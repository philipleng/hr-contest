"""生成参赛演示用的人才池数据（默认 500 条）。

用法（在 backend 目录下运行）：

    cd backend
    .\\venv\\Scripts\\python.exe seed_demo.py --total 500 --days 28 --yes

容器内（参赛部署机执行）：

    docker compose exec backend python seed_demo.py --total 500 --days 28 --yes

安全限制：
- 默认只允许 DB_HOST 为 127.0.0.1 / localhost / host.docker.internal / mysql；
  其他地址必须显式设置 ALLOW_REMOTE_SEED=1 才放行。
- 必须带 --yes 才会真正清空并写入；不带时只打印目标库与将要生成的数量。

行为：清空 applicant / resume_document / candidate_source / status_history /
      interview_record / contact_log / import_batch（保留 staff），再灌入演示数据。
      演示数据全部为随机生成的虚构信息，不对应任何真实申请人。
手机号归一化直接调用 app.utils.phone.normalize_ph_phone，不在本脚本重复实现。
"""

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
from sqlalchemy import text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from app.config import settings
from app.database import SessionLocal
from app.utils.phone import normalize_ph_phone

MEDIA_SRC = BACKEND / "demo_media"
UPLOAD_SEED = BACKEND / "app" / "uploads" / "local" / "seed"
RESUME_SEED = BACKEND / "app" / "private_uploads" / "resume" / "seed"

RNG = random.Random(20261117)

# 状态分布：让后台每个状态与看板都有内容
STATUS_RATIO = [
    ("new", 0.30),
    ("contacted", 0.20),
    ("interview1", 0.15),
    ("interview2", 0.10),
    ("interview3", 0.05),
    ("hired", 0.08),
    ("lost", 0.07),
    ("rejected", 0.05),
]
# 来源分布：自助 / 扫楼代录各四成
SOURCE_RATIO = [
    ("self", 0.40),
    ("staff", 0.40),
    ("referral", 0.10),
    ("import", 0.10),
]
GENDER_NULL_RATIO = 0.08

# 状态流转链路（不含起始 new）
STATUS_CHAIN = {
    "new": [],
    "contacted": ["contacted"],
    "interview1": ["contacted", "interview1"],
    "interview2": ["contacted", "interview1", "interview2"],
    "interview3": ["contacted", "interview1", "interview2", "interview3"],
    "hired": ["contacted", "interview1", "interview2", "interview3", "hired"],
    "lost": ["contacted", "lost"],
    "rejected": ["contacted", "rejected"],
}
STAGE_ROUND = {"interview1": 1, "interview2": 2, "interview3": 3, "hired": 3}

FIRST_NAMES = [
    "Juan", "Maria", "Jose", "Ana", "Mark", "Angel", "Carlo", "Joy", "Ramon", "Liza",
    "Paolo", "Grace", "Miguel", "Rosa", "Jomar", "Kristine", "Rey", "Michelle", "Danilo", "Aileen",
    "Arnel", "Jasmine", "Noel", "Cherry", "Rodel", "Maricar", "Elmer", "Divine", "Ryan", "Princess",
    "Rico", "May", "Joel", "Sarah", "Dennis", "Catherine", "Alvin", "Nicole", "Eduardo", "Faith",
]
LAST_NAMES = [
    "Dela Cruz", "Reyes", "Santos", "Garcia", "Mendoza", "Bautista", "Ramos", "Aquino",
    "Castillo", "Villanueva", "Navarro", "Torres", "Flores", "Gonzales", "Rivera", "Fernandez",
    "Cruz", "Diaz", "Lopez", "Perez", "Santiago", "Ramirez", "Cortez", "Domingo", "Salazar",
    "Mercado", "Aguilar", "Manalo", "Padilla", "Tolentino",
]
MIDDLE_NAMES = [
    "Santos", "Reyes", "Cruz", "Garcia", "Mendoza", "Bautista", "Ramos", "Flores", "Castro", "Ocampo",
]
CITIES = [
    "Quezon City", "Manila", "Caloocan", "Makati", "Pasig",
    "Taguig", "Paranaque", "Las Pinas", "Valenzuela", "Muntinlupa",
]
BARANGAYS = [
    "Poblacion", "San Antonio", "Bagong Silang", "Commonwealth", "Talipapa",
    "Malinta", "Baclaran", "Bangkal", "Ugong", "Sucat",
]
JOBS = [
    "Customer Service Representative", "Cashier", "Delivery Driver", "Housemaid",
    "Warehouse Staff", "Restaurant Crew", "Data Encoder", "Sales Associate",
    "Factory Worker", "Front Desk",
]
TAGS = [
    "bpo", "cashier", "driver", "household", "warehouse",
    "service-crew", "english-fluent", "encoder", "sales", "factory",
]
EDUCATIONS = ["high school", "college", "vocational"]
SPECIAL_NAMES = [
    ("María", "Santísima"), ("Nono", "Dela Cruz"), ("Anne-Marie", "O'Brien"),
    ("Jean & Joy", "Reyes"), ("Li", "Lei"), ("D'Angelo", "Cruz"),
    ("Ma. Cristina", "Bautista"), ("Jose Jr.", "Rizal"), ("Aisha", "Al-Amin"),
    ("Bjorn", "Garcia"),
]
DEMO_STAFF = [
    ("demo_lead_01", "扫楼一组 · 组长"),
    ("demo_lead_02", "扫楼二组 · 组长"),
    ("demo_lead_03", "企业交付 · 顾问"),
]
CONTACT_NOTES = [
    "已加 Messenger，约明天下午面试",
    "电话未接，稍后再拨",
    "确认可接受最低薪资",
    "需要住家安排，已说明",
    "重复号码，已合并备注",
]


def die(message: str) -> None:
    print(f"[seed] 中止：{message}")
    sys.exit(1)


def guard_environment(yes: bool) -> None:
    """只允许本机或容器内网地址，防止误清线上数据。"""
    allowed_hosts = {"127.0.0.1", "localhost", "host.docker.internal", "mysql"}
    url = make_url(settings.database_url)
    host = url.host or ""
    if host not in allowed_hosts and os.getenv("ALLOW_REMOTE_SEED") != "1":
        die(
            f"目标库主机 {host} 不在允许名单 {sorted(allowed_hosts)}；"
            "如确认是隔离的演示库，请设置 ALLOW_REMOTE_SEED=1"
        )
    print(f"[seed] 目标库 {host}:{url.port or 3306}/{url.database}")
    if not yes:
        print("[seed] 未带 --yes，仅打印信息，不做任何写入。")
        sys.exit(0)


def expand_ratio(ratios: list[tuple[str, float]], total: int) -> dict[str, int]:
    counts = {name: int(total * ratio) for name, ratio in ratios}
    remainder = total - sum(counts.values())
    if remainder:
        counts[ratios[0][0]] += remainder
    return counts


def mobile_digits(allow_dito: bool) -> str:
    """返回 10 位移动号码（首位 9）；allow_dito 时按 0895-0898 生成 DITO 号段。"""
    if allow_dito and RNG.random() < 0.15:
        return "89" + RNG.choice("5678") + "".join(
            RNG.choice("0123456789") for _ in range(7)
        )
    return "9" + "".join(RNG.choice("0123456789") for _ in range(9))


def build_phone(kind: str) -> str:
    if kind == "09":
        return "0" + mobile_digits(False)
    if kind == "+63":
        digits = mobile_digits(True)
        return f"+63 {digits[:3]} {digits[3:6]} {digits[6:]}"
    if kind == "63":
        return "63" + mobile_digits(True)
    if kind == "landline":
        return "02 " + "".join(RNG.choice("0123456789") for _ in range(8))
    return "09" + "".join(RNG.choice("0123456789") for _ in range(8))


def build_sample_pdf() -> bytes:
    """生成一个最小可用 PDF，供演示简历下载。"""
    stream = b"BT /F1 16 Tf 72 760 Td (Demo Resume - Seed Data) Tj ET"
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        (b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
         b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>"),
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj".encode() + body + b"endobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\n".encode()
    out += f"startxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


def prepare_seed_files() -> tuple[list[str], str, bytes]:
    """复制占位素材，返回照片 key 列表、视频 key、简历 PDF 字节。"""
    photos = sorted(MEDIA_SRC.glob("photo_*.jpg"))
    video = MEDIA_SRC / "sample_video.mp4"
    if len(photos) < 5 or not video.is_file():
        die(f"占位素材缺失，请检查 {MEDIA_SRC}")
    UPLOAD_SEED.mkdir(parents=True, exist_ok=True)
    for photo in photos:
        shutil.copy2(photo, UPLOAD_SEED / photo.name)
    shutil.copy2(video, UPLOAD_SEED / video.name)

    RESUME_SEED.mkdir(parents=True, exist_ok=True)
    pdf_bytes = build_sample_pdf()
    (RESUME_SEED / "sample_resume.pdf").write_bytes(pdf_bytes)

    photo_keys = [f"local/seed/{photo.name}" for photo in photos]
    print(f"[seed] 素材已就位：照片 {len(photo_keys)} 张、视频 1 段")
    return photo_keys, "local/seed/sample_video.mp4", pdf_bytes


def ensure_admin(db, password: str | None) -> None:
    """首次初始化时创建管理员账号；已存在则保留不动。"""
    row = db.execute(
        text("SELECT id FROM staff WHERE username = 'admin'")
    ).first()
    if row:
        if password:
            print("[seed] admin 账号已存在，忽略 --admin-password")
        return
    if not password:
        die(
            "admin 账号不存在。首次初始化请加 --admin-password '<自定义密码>'，"
            "否则无人能登录管理后台"
        )
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    db.execute(
        text(
            "INSERT INTO staff (username, password_hash, real_name, role, status) "
            "VALUES ('admin', :p, '系统管理员', 'admin', 'active')"
        ),
        {"p": hashed},
    )
    print("[seed] 已创建管理员账号 admin")


def ensure_demo_staff(db) -> list[int]:
    """确保有 3 个演示员工，供业绩归属与员工管理页展示（密码随机不可用）。"""
    ids: list[int] = []
    for username, real_name in DEMO_STAFF:
        row = db.execute(
            text("SELECT id FROM staff WHERE username = :u"), {"u": username}
        ).first()
        if row:
            ids.append(row[0])
            continue
        random_password = os.urandom(24).hex()
        hashed = bcrypt.hashpw(random_password.encode(), bcrypt.gensalt(rounds=12)).decode()
        db.execute(
            text(
                "INSERT INTO staff (username, password_hash, real_name, role, status) "
                "VALUES (:u, :p, :n, 'staff', 'active')"
            ),
            {"u": username, "p": hashed, "n": real_name},
        )
        ids.append(
            db.execute(
                text("SELECT id FROM staff WHERE username = :u"), {"u": username}
            ).first()[0]
        )
    return ids


def build_applicants(admin_id: int | None, operator_ids: list[int],
                     total: int, days: int) -> list[dict]:
    status_counts = expand_ratio(STATUS_RATIO, total)
    source_counts = expand_ratio(SOURCE_RATIO, total)

    statuses = [s for s, c in status_counts.items() for _ in range(c)]
    RNG.shuffle(statuses)
    source_types = [s for s, c in source_counts.items() for _ in range(c)]
    RNG.shuffle(source_types)

    kinds = (
        ["09"] * int(total * 0.60)
        + ["+63"] * int(total * 0.25)
        + ["63"] * int(total * 0.10)
        + ["landline"] * int(total * 0.03)
        + ["short"] * int(total * 0.02)
    )
    kinds += ["09"] * (total - len(kinds))
    RNG.shuffle(kinds)
    phones = [build_phone(kind) for kind in kinds]

    availabilities = (
        [1] * int(total * 0.40) + [2] * int(total * 0.30)
        + [0] * int(total * 0.20) + [3] * int(total * 0.10)
    )
    availabilities += [0] * (total - len(availabilities))
    RNG.shuffle(availabilities)

    now = datetime.now().replace(microsecond=0)
    name_pool = [(first, last) for first in FIRST_NAMES for last in LAST_NAMES]
    RNG.shuffle(name_pool)
    names = name_pool[:total]

    null_gender = set(RNG.sample(range(total), max(1, int(total * GENDER_NULL_RATIO))))
    rows: list[dict] = []
    for index in range(total):
        first, last = names[index]
        phone = phones[index]
        if index < 8:
            # 保证「今日新增」看板有数据
            created = now - timedelta(hours=RNG.randint(0, max(1, now.hour)))
        else:
            created = now - timedelta(
                days=RNG.randint(0, max(1, days - 1)),
                hours=RNG.randint(0, 23), minutes=RNG.randint(0, 59),
            )
        source_type = source_types[index]
        availability = availabilities[index]
        operator = operator_ids[index % len(operator_ids)] if operator_ids else admin_id
        rows.append({
            "first_name": first,
            "middle_name": RNG.choice(MIDDLE_NAMES) if RNG.random() > 0.3 else None,
            "last_name": last,
            "gender": None if index in null_gender else RNG.choice(["male", "female"]),
            "birth_date": datetime(
                RNG.randint(1980, 2007), RNG.randint(1, 12), RNG.randint(1, 28)
            ).date(),
            "nationality": "Filipino",
            "phone": phone,
            "phone_normalized": normalize_ph_phone(phone),
            "email": f"{first.lower().replace(' ', '')}.{last.lower().replace(' ', '')}"
                     f"{index}@example.com" if RNG.random() > 0.5 else None,
            "address_city": RNG.choice(CITIES),
            "address_barangay": RNG.choice(BARANGAYS),
            "target_job": RNG.choice(JOBS),
            "expected_salary": RNG.choice([13000, 15000, 16000, 18000, 20000, 25000]),
            "available_time": RNG.choice(["anytime", "2weeks", "1month"]),
            "availability": availability,
            "available_from": (now + timedelta(days=RNG.randint(0, 30))).date()
                              if availability == 1 else None,
            "work_type": RNG.choice(["fulltime", "parttime", "temp"]),
            "preferred_location": RNG.choice(CITIES),
            "live_in_ok": 1 if RNG.random() > 0.6 else 0,
            "education": RNG.choice(EDUCATIONS),
            "english_level": RNG.choice(["none", "basic", "fluent", "fluent"]),
            "chinese_level": RNG.choice(["none", "none", "basic"]),
            "last_job": RNG.choice(JOBS),
            "work_experience": f"{RNG.randint(0, 10)} 年相关经验",
            "photo_oss_key": None,
            "video_oss_key": None,
            "source_type": source_type,
            "source_ref": (
                f"STF{operator_ids[index % len(operator_ids)]:03d}"
                if source_type == "staff" and operator_ids else None
            ),
            "referrer_phone": build_phone("09") if source_type == "referral" else None,
            "applicant_remark": RNG.choice([
                "可立即到岗", "希望靠近住处", "有 BPO 经验", "需要住家安排", "有驾照",
            ]),
            "status": statuses[index],
            "created_by": operator if source_type == "staff" else None,
            "privacy_agreed_at": created + timedelta(minutes=RNG.randint(1, 10)),
            "intent_tags": None,
            "created_at": created,
            "updated_at": created,
        })

    # 脏数据：同名不同手机号（前 10 组）
    for offset in range(min(10, total // 4)):
        rows[10 + offset]["first_name"] = rows[offset]["first_name"]
        rows[10 + offset]["last_name"] = rows[offset]["last_name"]

    # 脏数据：同一手机号不同姓名
    for offset in range(min(6, total // 8)):
        rows[total - 1 - offset]["phone"] = rows[offset]["phone"]
        rows[total - 1 - offset]["phone_normalized"] = rows[offset]["phone_normalized"]

    # 脏数据：特殊字符姓名
    for offset, (first, last) in enumerate(SPECIAL_NAMES):
        target = total - 10 + offset
        if 0 <= target < total:
            rows[target]["first_name"] = first
            rows[target]["last_name"] = last

    # 意向标签：六成有值，每条 1-3 个
    for index in RNG.sample(range(total), int(total * 0.6)):
        rows[index]["intent_tags"] = ",".join(sorted(RNG.sample(TAGS, RNG.randint(1, 3))))

    return rows


def assign_media(rows: list[dict], photo_keys: list[str], video_key: str) -> None:
    total = len(rows)
    for index in RNG.sample(range(total), int(total * 0.6)):
        rows[index]["photo_oss_key"] = photo_keys[index % len(photo_keys)]
    for index in RNG.sample(range(total), int(total * 0.2)):
        rows[index]["video_oss_key"] = video_key


def build_resume_rows(rows: list[dict], pdf_bytes: bytes) -> list[dict]:
    """七成人有简历，其中一成人两份。"""
    total = len(rows)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    size = len(pdf_bytes)
    resume_rows: list[dict] = []
    owners = RNG.sample(range(total), int(total * 0.7))
    for index in owners:
        owner = rows[index]
        state = RNG.choice([1] * 85 + [0] * 8 + [2] * 4 + [3] * 2 + [4] * 1)
        created = owner["created_at"] + timedelta(days=RNG.randint(0, 2))
        resume_rows.append({
            "applicant_id": index + 1,
            "oss_key": "resume/seed/sample_resume.pdf",
            "file_name": f"{owner['first_name']}_{owner['last_name']}_Resume.pdf",
            "file_ext": ".pdf",
            "file_size": size,
            "content_hash": None if state == 4 else digest,
            "extract_state": state,
            "created_at": created,
            "updated_at": created,
        })
    for index in RNG.sample(owners, max(1, int(len(owners) * 0.1))):
        owner = rows[index]
        created = owner["created_at"] + timedelta(days=RNG.randint(5, 20))
        resume_rows.append({
            "applicant_id": index + 1,
            "oss_key": "resume/seed/sample_resume.pdf",
            "file_name": f"{owner['first_name']}_{owner['last_name']}_Resume_v2.pdf",
            "file_ext": ".pdf",
            "file_size": size,
            "content_hash": digest,
            "extract_state": 1,
            "created_at": created,
            "updated_at": created,
        })
    return resume_rows


def build_source_rows(rows: list[dict]) -> list[dict]:
    platform_map = {
        "self": ["facebook", "walkin", "jobstreet"],
        "staff": ["staff"],
        "referral": ["referral"],
        "import": ["import"],
    }
    source_rows: list[dict] = []
    for index, row in enumerate(rows):
        platform = RNG.choice(platform_map[row["source_type"]])
        profile_id = None
        source_url = None
        raw_payload = None
        if platform in ("facebook", "jobstreet"):
            prefix = "FB" if platform == "facebook" else "JS"
            profile_id = f"{prefix}{index + 1:06d}"
            source_url = (
                f"https://facebook.com/profile/{profile_id}"
                if platform == "facebook"
                else f"https://jobstreet.com/ph/profile/{profile_id}"
            )
        if platform == "import":
            raw_payload = json.dumps(
                {"source": "csv", "row": index + 1, "phone": row["phone"]},
                ensure_ascii=False,
            )
        created = row["created_at"]
        source_rows.append({
            "applicant_id": index + 1,
            "platform": platform,
            "platform_profile_id": profile_id,
            "source_url": source_url,
            "raw_payload": raw_payload,
            "payload_truncated": 0,
            "first_seen_at": created,
            "last_seen_at": created,
            "created_at": created,
        })
    return source_rows


def build_history_rows(rows: list[dict], operator_ids: list[int]) -> list[dict]:
    """按最终状态反推状态流转时间轴，让详情页时间轴有内容。"""
    history: list[dict] = []
    for index, row in enumerate(rows):
        chain = STATUS_CHAIN.get(row["status"], [])
        from_status = "new"
        moment = row["created_at"]
        for step in chain:
            moment = moment + timedelta(
                hours=RNG.randint(2, 30), minutes=RNG.randint(0, 59)
            )
            operator = operator_ids[index % len(operator_ids)] if operator_ids else None
            history.append({
                "applicant_id": index + 1,
                "from_status": from_status,
                "to_status": step,
                "operator_id": operator,
                "note": None,
                "created_at": moment,
            })
            from_status = step
    return history


def build_interview_rows(rows: list[dict], operator_ids: list[int]) -> list[dict]:
    """面试阶段与已雇佣的人生成面试记录；最后一轮可能是待定。"""
    interviews: list[dict] = []
    for index, row in enumerate(rows):
        stage_round = STAGE_ROUND.get(row["status"])
        if not stage_round:
            continue
        operator = operator_ids[index % len(operator_ids)] if operator_ids else None
        moment = row["created_at"]
        for round_no in range(1, stage_round + 1):
            moment = moment + timedelta(
                days=RNG.randint(1, 4), hours=RNG.randint(0, 8)
            )
            is_last = round_no == stage_round
            if row["status"] == "hired":
                result = "pass"
            elif is_last and row["status"] == "interview1":
                result = RNG.choice(["pass", "pending", "pending"])
            else:
                result = "pass" if not is_last else "pending"
            interviews.append({
                "applicant_id": index + 1,
                "round": round_no,
                "interview_at": moment,
                "result": result,
                "comment": RNG.choice([
                    "沟通表达清晰，可进入下一轮",
                    "有相关岗位经验，薪资待确认",
                    "英语可日常沟通",
                    "需要确认到岗时间",
                ]),
                "operator_id": operator,
                "created_at": moment,
            })
    return interviews


def build_contact_rows(rows: list[dict], operator_ids: list[int]) -> list[dict]:
    """已联系及之后的状态生成联系记录；部分带未来跟进时间，填充待跟进页。"""
    contacts: list[dict] = []
    now = datetime.now().replace(microsecond=0)
    for index, row in enumerate(rows):
        if row["status"] == "new":
            continue
        operator = operator_ids[index % len(operator_ids)] if operator_ids else None
        moment = row["created_at"] + timedelta(
            hours=RNG.randint(1, 24), minutes=RNG.randint(0, 59)
        )
        next_follow = None
        if RNG.random() < 0.4:
            # 待跟进页只看「今天到期或已逾期」，因此这里必须落在今天及以前
            next_follow = now - timedelta(days=RNG.randint(0, 6), hours=RNG.randint(0, 8))
        contacts.append({
            "applicant_id": index + 1,
            "channel": RNG.choice(["phone", "sms", "whatsapp", "messenger", "inperson"]),
            "result": RNG.choice([
                "reached", "reached", "no_answer", "interview_booked",
            ]),
            "note": RNG.choice(CONTACT_NOTES),
            "operator_id": operator,
            "next_follow_at": next_follow,
            "created_at": moment,
        })
    return contacts


def build_import_batches(rows: list[dict], operator_ids: list[int]) -> list[dict]:
    """为 import 来源的申请人补 3 个批次，让批量导入页有真实感的历史记录。"""
    import_indices = [i for i, row in enumerate(rows) if row["source_type"] == "import"]
    if not import_indices:
        return []
    batches: list[dict] = []
    chunk_count = min(3, len(import_indices))
    chunk_size = max(1, len(import_indices) // chunk_count)
    chunks = [import_indices[i:i + chunk_size] for i in range(0, len(import_indices), chunk_size)]
    # 均分成 3 组，避免余数单独成批
    if len(chunks) > chunk_count:
        tail = chunks[chunk_count - 1:]
        chunks = chunks[:chunk_count - 1] + [[i for chunk in tail for i in chunk]]
    names = [
        "quezon-city-walkin-batch-01.xlsx",
        "manila-bedspace-batch-02.xlsx",
        "caloocan-referral-batch-03.xlsx",
    ]
    for position, chunk in enumerate(chunks):
        if not chunk:
            continue
        first_created = min(rows[i]["created_at"] for i in chunk)
        fail_count = RNG.randint(1, 3)
        fail_detail = "\n".join(
            f"第 {RNG.randint(2, len(chunk) + 5)} 行：手机号格式无法识别"
            for _ in range(fail_count)
        )
        batches.append({
            "file_name": names[position % len(names)],
            "total_count": len(chunk) + fail_count,
            "success_count": len(chunk),
            "fail_count": fail_count,
            "fail_detail": fail_detail,
            "operator_id": operator_ids[position % len(operator_ids)] if operator_ids else None,
            "created_at": first_created - timedelta(minutes=RNG.randint(5, 120)),
        })
    return batches


APPLICANT_SQL = text("""
INSERT INTO applicant (
  first_name, middle_name, last_name, gender, birth_date, nationality,
  phone, phone_normalized, email, address_city, address_barangay,
  target_job, expected_salary, available_time, availability, available_from,
  work_type, preferred_location, live_in_ok, education, english_level,
  chinese_level, last_job, work_experience, photo_oss_key, video_oss_key,
  source_type, source_ref, referrer_phone, applicant_remark, status,
  created_by, privacy_agreed_at, intent_tags, created_at, updated_at
) VALUES (
  :first_name, :middle_name, :last_name, :gender, :birth_date, :nationality,
  :phone, :phone_normalized, :email, :address_city, :address_barangay,
  :target_job, :expected_salary, :available_time, :availability, :available_from,
  :work_type, :preferred_location, :live_in_ok, :education, :english_level,
  :chinese_level, :last_job, :work_experience, :photo_oss_key, :video_oss_key,
  :source_type, :source_ref, :referrer_phone, :applicant_remark, :status,
  :created_by, :privacy_agreed_at, :intent_tags, :created_at, :updated_at
)
""")

RESUME_SQL = text("""
INSERT INTO resume_document (
  applicant_id, oss_key, file_name, file_ext, file_size,
  content_hash, extract_state, created_at, updated_at
) VALUES (
  :applicant_id, :oss_key, :file_name, :file_ext, :file_size,
  :content_hash, :extract_state, :created_at, :updated_at
)
""")

SOURCE_SQL = text("""
INSERT INTO candidate_source (
  applicant_id, platform, platform_profile_id, source_url,
  raw_payload, payload_truncated, first_seen_at, last_seen_at, created_at
) VALUES (
  :applicant_id, :platform, :platform_profile_id, :source_url,
  :raw_payload, :payload_truncated, :first_seen_at, :last_seen_at, :created_at
)
""")

HISTORY_SQL = text("""
INSERT INTO status_history (
  applicant_id, from_status, to_status, operator_id, note, created_at
) VALUES (
  :applicant_id, :from_status, :to_status, :operator_id, :note, :created_at
)
""")

INTERVIEW_SQL = text("""
INSERT INTO interview_record (
  applicant_id, round, interview_at, result, comment, operator_id, created_at
) VALUES (
  :applicant_id, :round, :interview_at, :result, :comment, :operator_id, :created_at
)
""")

CONTACT_SQL = text("""
INSERT INTO contact_log (
  applicant_id, channel, result, note, operator_id, next_follow_at, created_at
) VALUES (
  :applicant_id, :channel, :result, :note, :operator_id, :next_follow_at, :created_at
)
""")

BATCH_SQL = text("""
INSERT INTO import_batch (
  file_name, total_count, success_count, fail_count, fail_detail, operator_id, created_at
) VALUES (
  :file_name, :total_count, :success_count, :fail_count, :fail_detail, :operator_id, :created_at
)
""")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成参赛演示用人才池数据")
    parser.add_argument("--total", type=int, default=500, help="生成条数，默认 500")
    parser.add_argument("--days", type=int, default=28, help="创建时间跨度天数，默认 28")
    parser.add_argument(
        "--admin-password",
        default=None,
        help="首次初始化时创建 admin 账号所用密码；账号已存在时忽略",
    )
    parser.add_argument("--yes", action="store_true", help="确认清空现有演示数据并写入")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    guard_environment(args.yes)
    total = max(1, args.total)
    days = max(1, args.days)
    photo_keys, video_key, pdf_bytes = prepare_seed_files()

    with SessionLocal() as db:
        ensure_admin(db, args.admin_password)
        admin_row = db.execute(text("SELECT id FROM staff ORDER BY id LIMIT 1")).first()
        admin_id = admin_row[0] if admin_row else None
        operator_ids = ensure_demo_staff(db)
        db.commit()

        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("status_history", "interview_record", "contact_log",
                      "resume_document", "candidate_source", "import_batch", "applicant"):
            db.execute(text(f"TRUNCATE TABLE {table}"))
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        rows = build_applicants(admin_id, operator_ids, total, days)
        assign_media(rows, photo_keys, video_key)
        db.execute(APPLICANT_SQL, rows)

        ids = [row[0] for row in db.execute(text("SELECT id FROM applicant ORDER BY id"))]
        if ids != list(range(1, total + 1)):
            db.rollback()
            die(f"applicant 自增 ID 不是 1..{total}，脚本依赖该顺序，已回滚")

        resume_rows = build_resume_rows(rows, pdf_bytes)
        history_rows = build_history_rows(rows, operator_ids)
        interview_rows = build_interview_rows(rows, operator_ids)
        contact_rows = build_contact_rows(rows, operator_ids)
        batch_rows = build_import_batches(rows, operator_ids)

        db.execute(RESUME_SQL, resume_rows)
        db.execute(SOURCE_SQL, build_source_rows(rows))
        db.execute(HISTORY_SQL, history_rows)
        db.execute(INTERVIEW_SQL, interview_rows)
        db.execute(CONTACT_SQL, contact_rows)
        db.execute(BATCH_SQL, batch_rows)
        db.commit()

    print(
        f"[seed] applicant {total} 条、resume_document {len(resume_rows)} 条、"
        f"status_history {len(history_rows)} 条、interview_record {len(interview_rows)} 条、"
        f"contact_log {len(contact_rows)} 条、import_batch {len(batch_rows)} 个"
    )
    print_stats()


def print_stats() -> None:
    with SessionLocal() as db:
        def one(sql: str):
            return db.execute(text(sql)).first()

        total, cleaned, failed = one(
            "SELECT COUNT(*), SUM(phone_normalized IS NOT NULL), "
            "SUM(phone_normalized IS NULL) FROM applicant"
        )
        print("\n=== 手机号清洁效果 ===")
        print(f"总数 {total}，归一化成功 {cleaned}，失败 {failed}，"
              f"清洁率 {cleaned / total:.1%}")

        print("\n原始格式样本（成功）：")
        for phone, normalized in db.execute(text(
            "SELECT phone, phone_normalized FROM applicant "
            "WHERE phone_normalized IS NOT NULL ORDER BY id LIMIT 5"
        )):
            print(f"  {phone!r:<26} -> {normalized}")

        print("\n=== 数量核对 ===")
        for label, sql in (
            ("状态分布", ("SELECT status, COUNT(*) FROM applicant "
                        "GROUP BY status ORDER BY COUNT(*) DESC")),
            ("来源分布", ("SELECT source_type, COUNT(*) FROM applicant "
                        "GROUP BY source_type ORDER BY COUNT(*) DESC")),
            ("gender 未填写", "SELECT COUNT(*) FROM applicant WHERE gender IS NULL"),
            ("resume_document", "SELECT COUNT(*) FROM resume_document"),
            ("candidate_source", "SELECT COUNT(*) FROM candidate_source"),
            ("status_history", "SELECT COUNT(*) FROM status_history"),
            ("interview_record", "SELECT COUNT(*) FROM interview_record"),
            ("contact_log", "SELECT COUNT(*) FROM contact_log"),
            ("待跟进（今天到期或逾期）",
             "SELECT COUNT(*) FROM contact_log "
             "WHERE next_follow_at < DATE_ADD(CURDATE(), INTERVAL 1 DAY)"),
            ("import_batch", "SELECT COUNT(*) FROM import_batch"),
            ("有照片", "SELECT COUNT(*) FROM applicant WHERE photo_oss_key IS NOT NULL"),
            ("有视频", "SELECT COUNT(*) FROM applicant WHERE video_oss_key IS NOT NULL"),
            ("有标签", "SELECT COUNT(*) FROM applicant WHERE intent_tags IS NOT NULL"),
        ):
            rows = db.execute(text(sql)).all()
            if label in ("状态分布", "来源分布"):
                detail = "，".join(f"{name}={count}" for name, count in rows)
                print(f"  {label}: {detail}")
            else:
                print(f"  {label}: {rows[0][0]}")


if __name__ == "__main__":
    main()
