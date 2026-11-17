"""LST 组 P0 用例：申请人列表的性别 / 年龄筛选与排序

年龄筛选在后端被翻译成 birth_date 闭区间（不依赖 MySQL 的函数索引），
这里用相对今天的生日构造数据，断言「区间边界」和「生日为空时被排除」。
"""

from datetime import datetime, timedelta

from app.models import Applicant
from app.utils.tz import now_local, today_local

LIST = "/api/applicant/list"


def _years_ago(years: int) -> str:
    """构造 N 年前的生日（2/29 落到非闰年时退到 2/28）"""
    today = today_local()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def _submit(client, payload, phone: str, **overrides):
    body = payload(phone=phone, **overrides)
    resp = client.post("/api/applicant/submit", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["applicant_id"]


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["data"]["items"]]


def test_lst_01_gender_filter(client, admin_headers, submit_payload):
    """LST-01 性别筛选：male / female / unspecified 各自只返回对应记录"""
    male_id = _submit(client, submit_payload, "09171000001", first_name="Mario", gender="male")
    female_id = _submit(client, submit_payload, "09171000002", first_name="Maria", gender="female")
    null_id = _submit(client, submit_payload, "09171000003", first_name="Alex", gender=None)

    assert _ids(client.get(LIST, params={"gender": "male"}, headers=admin_headers)) == [male_id]
    assert _ids(client.get(LIST, params={"gender": "female"}, headers=admin_headers)) == [female_id]
    # 未填写是刻意设计的空值，必须能单独筛出来
    assert _ids(client.get(LIST, params={"gender": "unspecified"}, headers=admin_headers)) == [null_id]


def test_lst_02_age_range_bounds(client, admin_headers, submit_payload):
    """LST-02 年龄区间：边界按「生日当天算满岁」，区间外与无生日记录都被排除"""
    age_20 = _submit(client, submit_payload, "09172000001", first_name="Twenty", birth_date=_years_ago(20))
    age_45 = _submit(client, submit_payload, "09172000002", first_name="FortyFive", birth_date=_years_ago(45))
    no_birth = _submit(client, submit_payload, "09172000003", first_name="NoBirth")

    young = _ids(client.get(
        LIST, params={"age_min": 18, "age_max": 25}, headers=admin_headers,
    ))
    assert young == [age_20]

    senior = _ids(client.get(
        LIST, params={"age_min": 40, "age_max": 60}, headers=admin_headers,
    ))
    assert senior == [age_45]

    # 只给下界时，没填生日的记录同样不能混进来
    everything_with_birth = _ids(client.get(
        LIST, params={"age_min": 0, "age_max": 120}, headers=admin_headers,
    ))
    assert set(everything_with_birth) == {age_20, age_45}
    assert no_birth not in everything_with_birth


def test_lst_03_sort_by_birth_date(client, admin_headers, submit_payload):
    """LST-03 排序：birth_date 升序 / 默认 created_at 倒序"""
    oldest = _submit(client, submit_payload, "09173000001", first_name="Oldest", birth_date=_years_ago(50))
    youngest = _submit(client, submit_payload, "09173000002", first_name="Youngest", birth_date=_years_ago(18))
    middle = _submit(client, submit_payload, "09173000003", first_name="Middle", birth_date=_years_ago(30))

    asc = _ids(client.get(
        LIST, params={"sort_by": "birth_date", "order": "asc"}, headers=admin_headers,
    ))
    assert asc == [oldest, middle, youngest]

    desc = _ids(client.get(
        LIST, params={"sort_by": "birth_date", "order": "desc"}, headers=admin_headers,
    ))
    assert desc == [youngest, middle, oldest]

    # 默认按录入时间倒序，最后录入的排最前
    default_order = _ids(client.get(LIST, headers=admin_headers))
    assert default_order[0] == middle


def test_lst_04_null_birth_date_sorts_last(client, admin_headers, submit_payload):
    """LST-04 按生日排序时，没填生日的人固定排在最后（升序降序都一样）"""
    _submit(client, submit_payload, "09173500001", first_name="Young", birth_date=_years_ago(20))
    _submit(client, submit_payload, "09173500002", first_name="Old", birth_date=_years_ago(50))
    no_birth = _submit(client, submit_payload, "09173500003", first_name="NoBirth")

    for order in ("asc", "desc"):
        resp = client.get(
            LIST, params={"sort_by": "birth_date", "order": order}, headers=admin_headers,
        )
        items = resp.json()["data"]["items"]
        assert items[-1]["id"] == no_birth, f"{order}: {[i['first_name'] for i in items]}"
        assert items[-1]["birth_date"] is None


def test_lst_05_invalid_params(client, admin_headers, submit_payload):
    """LST-05 非法参数：排序字段不在白名单 → 422；年龄下界大于上界 → 400"""
    _submit(client, submit_payload, "09174000001")

    bad_sort = client.get(
        LIST, params={"sort_by": "created_at desc; drop table applicant"},
        headers=admin_headers,
    )
    assert bad_sort.status_code == 422

    bad_age = client.get(
        LIST, params={"age_min": 40, "age_max": 20}, headers=admin_headers,
    )
    assert bad_age.status_code == 400


def test_lst_06_date_range_half_open_and_today_stats(client, db_session, admin_headers):
    """LST-06 半开日期区间与今日统计：23:59:59 命中、次日 00:00:00 排除"""
    in_end = Applicant(
        first_name="EndSec",
        last_name="Boundary",
        phone="09175000001",
        created_at=datetime(2026, 2, 28, 23, 59, 59),
        updated_at=datetime(2026, 2, 28, 23, 59, 59),
    )
    next_day = Applicant(
        first_name="NextDay",
        last_name="Boundary",
        phone="09175000002",
        created_at=datetime(2026, 3, 1, 0, 0, 0),
        updated_at=datetime(2026, 3, 1, 0, 0, 0),
    )
    today_now = now_local()
    today_item = Applicant(
        first_name="Today",
        last_name="Now",
        phone="09175000003",
        created_at=today_now,
        updated_at=today_now,
    )
    yesterday_item = Applicant(
        first_name="Yesterday",
        last_name="Old",
        phone="09175000004",
        created_at=today_now - timedelta(days=1),
        updated_at=today_now - timedelta(days=1),
    )
    db_session.add_all([in_end, next_day, today_item, yesterday_item])
    db_session.commit()

    range_ids = _ids(
        client.get(
            LIST,
            params={"start_date": "2026-02-28", "end_date": "2026-02-28"},
            headers=admin_headers,
        )
    )
    assert range_ids == [in_end.id]

    new_today_ids = _ids(client.get(LIST, params={"new_today": True}, headers=admin_headers))
    assert today_item.id in new_today_ids
    assert yesterday_item.id not in new_today_ids

    stats_resp = client.get("/api/applicant/stats/today", headers=admin_headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json()["data"] == {
        "today_total": 1,
        "today_pending": 1,
        "total": 4,
    }


def test_lst_07_availability_and_intent_tag_exact_boundary(
    client, db_session, admin_headers, submit_payload,
):
    """LST-07 availability 与 intent_tag 跨方言筛选：'bpo' 不误匹配 'bpo-night'"""
    id_bpo = _submit(client, submit_payload, "09176000001", first_name="ExactBpo")
    id_bpo_multi = _submit(client, submit_payload, "09176000002", first_name="MultiBpo")
    id_bpo_night = _submit(client, submit_payload, "09176000003", first_name="NightBpo")
    id_none = _submit(client, submit_payload, "09176000004", first_name="NoTags")

    db_session.get(Applicant, id_bpo).availability = 1
    db_session.get(Applicant, id_bpo).intent_tags = "bpo"
    db_session.get(Applicant, id_bpo_multi).availability = 2
    db_session.get(Applicant, id_bpo_multi).intent_tags = "cashier,bpo,sales"
    db_session.get(Applicant, id_bpo_night).availability = 1
    db_session.get(Applicant, id_bpo_night).intent_tags = "bpo-night,driver"
    db_session.get(Applicant, id_none).availability = 1
    db_session.get(Applicant, id_none).intent_tags = None
    db_session.commit()

    # 仅传 intent_tag=bpo：命中 bpo 与 cashier,bpo,sales，不误命中 bpo-night 与 NULL
    bpo_ids = _ids(client.get(LIST, params={"intent_tag": "bpo"}, headers=admin_headers))
    assert set(bpo_ids) == {id_bpo, id_bpo_multi}
    assert id_bpo_night not in bpo_ids
    assert id_none not in bpo_ids

    # availability=1 + intent_tag=bpo 组合筛选
    combo_ids = _ids(
        client.get(LIST, params={"availability": 1, "intent_tag": "bpo"}, headers=admin_headers)
    )
    assert combo_ids == [id_bpo]
