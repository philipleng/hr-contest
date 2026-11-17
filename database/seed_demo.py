"""生成 1000 条人才池演示数据（含脏数据）。

用法（必须在 backend 目录下运行，确保读到 backend/.env）：

    cd backend
    .\\venv\\Scripts\\python.exe ..\\database\\seed_demo.py

安全限制：DB_HOST 必须是 127.0.0.1，防止误连线上库。
行为：清空 applicant / resume_document / candidate_source / status_history /
      interview_record（保留 staff），重新灌 1000 条，并复制占位素材。

数据分布见 人才池数据模型演进方案3.0.md 第 5.3 / 5.4 节。
手机号归一化直接调用 app.utils.phone.normalize_ph_phone，不在本脚本重复实现。
"""

import hashlib
import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from app.config import settings
from app.database import SessionLocal
from app.utils.phone import normalize_ph_phone

MEDIA_SRC = ROOT / "test_resource"
UPLOAD_SEED = BACKEND / "app" / "uploads" / "local" / "seed"
RESUME_SEED = BACKEND / "app" / "private_uploads" / "resume" / "seed"

RNG = random.Random(20261113)
TOTAL = 1000

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

GARBAGE_PHONES = ["N/A", "12345", "not available", "00000000000", "-"]


def die(message: str) -> None:
    print(f"[seed] 中止：{message}")
    sys.exit(1)


def guard_environment() -> None:
    """只允许本地库，防止误清线上数据。"""
    if settings.DB_HOST != "127.0.0.1":
        die(f"DB_HOST={settings.DB_HOST}，本脚本只允许 127.0.0.1")
    print(f"[seed] 目标库 {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")


def mobile_digits(allow_dito: bool) -> str:
    """返回 10 位移动号码（首位 8/9）；allow_dito 时按 0895-0898 生成 DITO 号段。"""
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
    if kind == "short":
        return "09" + "".join(RNG.choice("0123456789") for _ in range(8))
    return RNG.choice(GARBAGE_PHONES)


def build_sample_pdf() -> bytes:
    """生成一个最小可用 PDF，供种子简历下载演示。"""
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


def build_applicants(admin_id: int | None) -> list[dict]:
    kinds = ["09"] * 600 + ["+63"] * 200 + ["63"] * 150
    kinds += ["landline"] * 20 + ["short"] * 15 + ["garbage"] * 15
    pairs = [(kind, build_phone(kind)) for kind in kinds]
    RNG.shuffle(pairs)
    kinds = [kind for kind, _ in pairs]
    phones = [phone for _, phone in pairs]

    statuses = (
        ["new"] * 300 + ["contacted"] * 200 + ["interview1"] * 100
        + ["interview2"] * 70 + ["interview3"] * 20 + ["hired"] * 80
        + ["rejected"] * 130 + ["lost"] * 100
    )
    RNG.shuffle(statuses)
    source_types = ["self"] * 500 + ["staff"] * 300 + ["referral"] * 150 + ["import"] * 50
    RNG.shuffle(source_types)
    availabilities = [1] * 400 + [2] * 300 + [0] * 200 + [3] * 100
    RNG.shuffle(availabilities)

    now = datetime.now().replace(microsecond=0)
    name_pool = [(first, last) for first in FIRST_NAMES for last in LAST_NAMES]
    RNG.shuffle(name_pool)
    names = name_pool[:TOTAL]
    rows: list[dict] = []
    for index in range(TOTAL):
        first, last = names[index]
        phone = phones[index]
        created = now - timedelta(
            days=RNG.randint(0, 179), hours=RNG.randint(0, 23), minutes=RNG.randint(0, 59)
        )
        source_type = source_types[index]
        availability = availabilities[index]
        rows.append({
            "first_name": first,
            "middle_name": RNG.choice(MIDDLE_NAMES) if RNG.random() > 0.3 else None,
            "last_name": last,
            "gender": RNG.choice(["male", "female", None]),
            "birth_date": datetime(
                RNG.randint(1970, 2005), RNG.randint(1, 12), RNG.randint(1, 28)
            ).date(),
            "nationality": "Filipino",
            "phone": phone,
            "phone_normalized": normalize_ph_phone(phone),
            "email": f"{first.lower().replace(' ', '')}.{last.lower().replace(' ', '')}"
                     f"{index}@example.com" if RNG.random() > 0.4 else None,
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
            "english_level": RNG.choice(["none", "basic", "fluent"]),
            "chinese_level": RNG.choice(["none", "none", "basic"]),
            "last_job": RNG.choice(JOBS),
            "work_experience": f"{RNG.randint(0, 10)} 年相关经验",
            "photo_oss_key": None,
            "video_oss_key": None,
            "source_type": source_type,
            "source_ref": f"STF{RNG.randint(1, 30):03d}" if source_type == "staff" else None,
            "referrer_phone": build_phone("09") if source_type == "referral" else None,
            "applicant_remark": RNG.choice([
                "可立即到岗", "希望靠近住处", "有 BPO 经验", "需要住家安排", "有驾照",
            ]),
            "status": statuses[index],
            "created_by": admin_id if source_type == "staff" else None,
            "privacy_agreed_at": created + timedelta(minutes=RNG.randint(1, 10)),
            "intent_tags": None,
            "created_at": created,
            "updated_at": created,
        })

    # 脏数据：同名不同手机号 10 组
    for offset in range(10):
        rows[20 + offset]["first_name"] = rows[offset]["first_name"]
        rows[20 + offset]["last_name"] = rows[offset]["last_name"]

    # 脏数据：同一手机号不同姓名 10 组（同格式内互换，保持格式分布不变）
    by_kind: dict[str, list[int]] = {}
    for index, kind in enumerate(kinds):
        by_kind.setdefault(kind, []).append(index)
    for kind, count in (("09", 4), ("+63", 3), ("63", 3)):
        picks = RNG.sample(by_kind[kind], count * 2)
        for pair_index in range(count):
            source, target = picks[pair_index * 2], picks[pair_index * 2 + 1]
            rows[target]["phone"] = rows[source]["phone"]
            rows[target]["phone_normalized"] = rows[source]["phone_normalized"]

    # 脏数据：特殊字符姓名 10 条
    for offset, (first, last) in enumerate(SPECIAL_NAMES):
        rows[900 + offset]["first_name"] = first
        rows[900 + offset]["last_name"] = last

    # 脏数据：超长备注 5 条
    long_text = "备注：" + "客户要求较多，需要反复确认工作时间与地点。" * 20
    for offset in range(5):
        rows[910 + offset]["applicant_remark"] = long_text

    # 意向标签：600 条有值，每条 1-3 个
    for index in RNG.sample(range(TOTAL), 600):
        count = RNG.randint(1, 3)
        rows[index]["intent_tags"] = ",".join(sorted(RNG.sample(TAGS, count)))

    # 媒体：300 条照片、100 条视频（在 main 里回填 key）
    return rows


def assign_media(rows: list[dict], photo_keys: list[str], video_key: str) -> None:
    for index in RNG.sample(range(TOTAL), 300):
        rows[index]["photo_oss_key"] = photo_keys[index % len(photo_keys)]
    for index in RNG.sample(range(TOTAL), 100):
        rows[index]["video_oss_key"] = video_key


def build_resume_rows(rows: list[dict], pdf_bytes: bytes) -> list[dict]:
    """700 人有简历，其中 100 人两份。"""
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    size = len(pdf_bytes)
    resume_rows: list[dict] = []
    owners = RNG.sample(range(TOTAL), 700)
    for index in owners:
        owner = rows[index]
        states = [1] * 85 + [0] * 8 + [2] * 4 + [3] * 2 + [4] * 1
        state = RNG.choice(states)
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
    for index in RNG.sample(owners, 100):
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


def main() -> None:
    guard_environment()
    photo_keys, video_key, pdf_bytes = prepare_seed_files()

    with SessionLocal() as db:
        admin_row = db.execute(text("SELECT id FROM staff ORDER BY id LIMIT 1")).first()
        admin_id = admin_row[0] if admin_row else None

        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("status_history", "interview_record", "resume_document",
                      "candidate_source", "applicant"):
            db.execute(text(f"TRUNCATE TABLE {table}"))
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        rows = build_applicants(admin_id)
        assign_media(rows, photo_keys, video_key)
        db.execute(APPLICANT_SQL, rows)

        ids = [row[0] for row in db.execute(text("SELECT id FROM applicant ORDER BY id"))]
        if ids != list(range(1, TOTAL + 1)):
            db.rollback()
            die("applicant 自增 ID 不是 1..1000，脚本依赖该顺序，已回滚")

        resume_rows = build_resume_rows(rows, pdf_bytes)
        db.execute(RESUME_SQL, resume_rows)
        db.execute(SOURCE_SQL, build_source_rows(rows))
        db.commit()

    print(f"[seed] applicant {TOTAL} 条、resume_document {len(resume_rows)} 条、"
          f"candidate_source {TOTAL} 条")
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

        print("失败样本：")
        for (phone,) in db.execute(text(
            "SELECT phone FROM applicant WHERE phone_normalized IS NULL ORDER BY id LIMIT 8"
        )):
            print(f"  {phone!r}")

        print("\n=== 数量核对 ===")
        for label, sql in (
            ("resume_document", "SELECT COUNT(*) FROM resume_document"),
            ("candidate_source", "SELECT COUNT(*) FROM candidate_source"),
            ("同名不同号组数", ("SELECT COUNT(*) FROM (SELECT first_name, last_name "
                              "FROM applicant GROUP BY first_name, last_name "
                              "HAVING COUNT(*) > 1) t")),
            ("同号不同名组数", ("SELECT COUNT(*) FROM (SELECT phone_normalized "
                              "FROM applicant WHERE phone_normalized IS NOT NULL "
                              "GROUP BY phone_normalized HAVING COUNT(*) > 1) t")),
            ("有照片", "SELECT COUNT(*) FROM applicant WHERE photo_oss_key IS NOT NULL"),
            ("有视频", "SELECT COUNT(*) FROM applicant WHERE video_oss_key IS NOT NULL"),
            ("有标签", "SELECT COUNT(*) FROM applicant WHERE intent_tags IS NOT NULL"),
        ):
            print(f"  {label}: {one(sql)[0]}")


if __name__ == "__main__":
    main()
