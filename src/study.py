"""Student registration, durable paired assessments, and faculty results."""
import csv
import hashlib
import hmac
import io
import json
import os
import random
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.assessment_bank import VERSION, PAIRS, CASE_PAIRS, bank_with_sources
from src.rash_assessment_bank import bank as rash_bank, IMAGE_DIR

COOKIE = "teaching_student"
SESSION_SECONDS = 30 * 86400
AUTO_POST_SECONDS = int(os.getenv("STUDY_AUTO_POST_SECONDS", str(30 * 60)))
HEARTBEAT_MAX_SECONDS = 20.0
HEARTBEAT_CLOCK_SLOP = 2.0
ROOT = Path(__file__).resolve().parents[1]
router = APIRouter()
SECTION_LABELS = {"basic": "基础知识", "rash": "皮疹辨别", "case": "模拟案例"}
DEFAULT_TEACHERS = {
    ("12345", "宋蕊"),
    ("12345", "田地"),
    ("12345", "穆雪纯"),
}


def question_section(question):
    return question.get("section", "case" if question.get("case_id") else "basic")


def section_scores(row):
    """Also derive module totals for archived papers without rewriting records."""
    if not row.get("result"):
        return {}
    result = json.loads(row["result"])
    if "sections" in result:
        return result["sections"]
    scores = {}
    answers = json.loads(row["answers"])
    for q in json.loads(row["paper"])["questions"]:
        key = question_section(q)
        entry = scores.setdefault(key, {"label": SECTION_LABELS[key], "score": 0, "total": 0})
        entry["total"] += q["points"]
        entry["score"] += q["points"] if answers.get(q["id"]) == q["correct"] else 0
    return scores


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def normalized_identity(student_no, name):
    return (unicodedata.normalize("NFKC", student_no).strip().upper(),
            unicodedata.normalize("NFKC", name).strip())


def teacher_identities():
    """Keep the named course faculty available while supporting local overrides."""
    identities = set(DEFAULT_TEACHERS)
    number, name = normalized_identity(os.getenv("TEACHER_STUDENT_NO", ""),
                                       os.getenv("TEACHER_NAME", ""))
    if number and name:
        identities.add((number, name))
    return identities


def is_teacher(user):
    return bool(user and normalized_identity(user["student_no"], user["name"]) in teacher_identities())


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate_student_identity_schema()
        with self.db() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS students (
              id TEXT PRIMARY KEY, student_no TEXT NOT NULL, name TEXT NOT NULL,
              first_form TEXT NOT NULL, created REAL NOT NULL,
              UNIQUE(student_no, name));
            CREATE TABLE IF NOT EXISTS sessions (
              hash TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES students(id), expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
              id TEXT PRIMARY KEY, student TEXT NOT NULL REFERENCES students(id), phase TEXT NOT NULL,
              form TEXT NOT NULL, version TEXT NOT NULL, paper TEXT NOT NULL,
              answers TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 0,
              started REAL NOT NULL, submitted REAL, result TEXT,
              UNIQUE(student, phase));
            CREATE TABLE IF NOT EXISTS activity (
              student TEXT NOT NULL REFERENCES students(id), module TEXT NOT NULL,
              count INTEGER NOT NULL DEFAULT 1, first REAL NOT NULL, last REAL NOT NULL,
              PRIMARY KEY(student, module));
            CREATE TABLE IF NOT EXISTS learning_time (
              student TEXT PRIMARY KEY REFERENCES students(id),
              seconds REAL NOT NULL DEFAULT 0, last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS study_history (
              id TEXT PRIMARY KEY, reset_at REAL NOT NULL,
              student_no TEXT NOT NULL, name TEXT NOT NULL,
              snapshot TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS study_history_reset ON study_history(reset_at);
            CREATE TABLE IF NOT EXISTS login_limits (key TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS login_time ON login_limits(created);
            """)
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('seed', ?)", (str(secrets.randbits(63)),))
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('post_open', 'false')")
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('post_updated', '0')")
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('version', ?)", (VERSION,))
        os.chmod(self.path, 0o600)
        # Keep every released bank's paired papers. This lets a student who began
        # an older pre-test receive the matching older post-test after an upgrade.
        settings = self.settings()
        previous = settings.get("version")
        with self.db(write=True) as c:
            if previous:
                for form in ("A", "B"):
                    legacy = settings.get(f"paper_{form}")
                    if legacy:
                        c.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)",
                                  (self.paper_key(previous, form), legacy))
            c.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)",
                      (self.seed_key(VERSION), str(secrets.randbits(63))))
            c.execute("INSERT INTO settings VALUES ('version', ?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (VERSION,))
        if self.paper_key(VERSION, "A") not in self.settings():
            forms = {form: self.build_paper(form) for form in ("A", "B")}
            with self.db(write=True) as c:
                for form, paper in forms.items():
                    c.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)",
                              (self.paper_key(VERSION, form), encode(paper)))

    def migrate_student_identity_schema(self):
        """Allow the same student number to be registered under distinct names.

        Older releases made ``student_no`` globally unique. The course now has
        multiple faculty members sharing one institutional number, so identity
        records are unique by the submitted name-number pair instead.
        """
        conn = sqlite3.connect(self.path, timeout=20)
        try:
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='students'").fetchone()
            if not schema:
                return
            indexes = []
            for index in conn.execute("PRAGMA index_list(students)"):
                if index[2]:
                    indexes.append(tuple(row[2] for row in conn.execute(f"PRAGMA index_info('{index[1]}')")))
            if ("student_no", "name") in indexes:
                return
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE students_identity_migration (
              id TEXT PRIMARY KEY, student_no TEXT NOT NULL, name TEXT NOT NULL,
              first_form TEXT NOT NULL, created REAL NOT NULL,
              UNIQUE(student_no, name))""")
            conn.execute("INSERT INTO students_identity_migration SELECT id,student_no,name,first_form,created FROM students")
            conn.execute("DROP TABLE students")
            conn.execute("ALTER TABLE students_identity_migration RENAME TO students")
            conn.commit()
            conn.execute("PRAGMA foreign_keys=ON")
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("学生身份表迁移后外键校验失败")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def paper_key(version, form):
        return f"paper::{version}::{form}"

    @staticmethod
    def seed_key(version):
        return f"seed::{version}"

    @contextmanager
    def db(self, write=False):
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def login(self, student_no, name, address):
        key = hashlib.sha256(f"{address}:{student_no}".encode()).hexdigest()
        now = time.time()
        # Commit the rate-limit event even if identity validation subsequently fails.
        with self.db(write=True) as c:
            c.execute("DELETE FROM login_limits WHERE created < ?", (now - 600,))
            if c.execute("SELECT COUNT(*) FROM login_limits WHERE key=?", (key,)).fetchone()[0] >= 40:
                raise HTTPException(429, "登录尝试较多，请10分钟后再试。")
            c.execute("INSERT INTO login_limits VALUES (?, ?)", (key, now))
        with self.db(write=True) as c:
            user = c.execute("SELECT * FROM students WHERE student_no=? AND name=?", (student_no, name)).fetchone()
            if not user:
                c.execute("INSERT INTO students VALUES (?, ?, ?, ?, ?)",
                          (secrets.token_hex(16), student_no, name, secrets.choice(["A", "B"]), now))
                user = c.execute("SELECT * FROM students WHERE student_no=? AND name=?", (student_no, name)).fetchone()
            token = secrets.token_urlsafe(32)
            c.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            c.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                      (hashlib.sha256(token.encode()).hexdigest(), user["id"], now + SESSION_SECONDS))
            return dict(user), token

    def user(self, token):
        if not token:
            return None
        with self.db() as c:
            row = c.execute("SELECT s.* FROM students s JOIN sessions t ON s.id=t.student WHERE t.hash=? AND t.expires>?",
                            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
            return dict(row) if row else None

    def settings(self):
        with self.db() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}

    def blueprint(self):
        settings = self.settings()
        rng = random.Random(int(settings.get(self.seed_key(VERSION), settings["seed"])))
        selected = []
        for difficulty, count in [("基础", 8), ("应用", 8), ("综合", 4)]:
            selected.extend(rng.sample([p for p in PAIRS if p["difficulty"] == difficulty], count))
        return selected

    def build_paper(self, form):
        sources = bank_with_sources()
        questions = []
        cases = []

        def add(q, ident, points, meta, case_id=None, section="basic"):
            choices = list(q["choices"])
            random.SystemRandom().shuffle(choices)
            options = [{"id": secrets.token_hex(5), "text": text} for text in choices]
            questions.append({"id": ident, "stem": q["stem"], "options": options,
                              "correct": next(o["id"] for o in options if o["text"] == q["answer"]),
                              "points": points, "case_id": case_id, "section": section, **meta,
                              **{k: q[k] for k in ("image_file", "image_source") if k in q}})

        for n, p in enumerate(self.blueprint(), 1):
            refs = [sources[k] for k in p["source_ids"]]
            add(p[form], f"q{n:02}", 3,
                dict(pair=p["id"], point=p["point"], domain=p["domain"], difficulty=p["difficulty"],
                     disease=refs[0]["disease"], explanation=p["explanation"],
                     sources=[{"id": r["id"], "document": r["document"], "url": r["source"]} for r in refs]))
        for n, p in enumerate(rash_bank(), 1):
            q = p[form]
            add(q, f"r{n:02}", 2,
                dict(pair=p["id"], point=p["point"], domain=p["domain"], difficulty=p["difficulty"],
                     disease=p["disease"], explanation=q["explanation"], sources=p["sources"]), section="rash")
        # Same two case constructs in both forms, with distinct patients and wording.
        for n, p in enumerate(reversed(CASE_PAIRS), 1):
            case_id = f"c{n}"
            cases.append({"id": case_id, "title": f"案例题 {n}", "background": p[form]["background"]})
            refs = [sources[k] for k in p["source_ids"]]
            for j, q in enumerate(p[form]["questions"]):
                add(q, f"{case_id}_{j+1}", 3,
                    dict(pair=f"{p['id']}-{j+1}", point=p["points"][j], domain=p["domains"][j],
                         difficulty=p["difficulty"], disease=p["disease"], explanation=p["explanations"][j],
                         sources=[{"id": r["id"], "document": r["document"], "url": r["source"]} for r in refs]), case_id, "case")
        return {"version": VERSION, "form": form, "questions": questions, "cases": cases, "total": 100}

    def make_paper(self, form, version=VERSION):
        settings = self.settings()
        key = self.paper_key(version, form)
        if key not in settings:
            raise HTTPException(409, "该测验版本的配对试卷不存在，请联系管理员。")
        paper = json.loads(settings[key])
        for question in paper["questions"]:
            for option in question["options"]:
                old_id = option["id"]
                option["id"] = secrets.token_hex(8)
                if question["correct"] == old_id:
                    question["correct"] = option["id"]
            random.SystemRandom().shuffle(question["options"])
        return paper

    def attempts(self, user_id):
        with self.db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM attempts WHERE student=? ORDER BY started", (user_id,))]

    @staticmethod
    def learning_seconds(user_id, c):
        row = c.execute("SELECT seconds FROM learning_time WHERE student=?", (user_id,)).fetchone()
        return float(row["seconds"]) if row else 0.0

    def post_access(self, user_id, c):
        manual = c.execute("SELECT value FROM settings WHERE key='post_open'").fetchone()[0] == "true"
        seconds = self.learning_seconds(user_id, c)
        automatic = seconds >= AUTO_POST_SECONDS
        return manual or automatic, "teacher" if manual else "time" if automatic else None, seconds

    def status(self, user):
        if is_teacher(user):
            return {"authenticated": True, "role": "teacher", "student": {"student_no": user["student_no"], "name": user["name"]},
                    "pre_completed": False, "post_completed": False, "post_open": self.settings()["post_open"] == "true", "active": None, "results": []}
        attempts = self.attempts(user["id"])
        pre = next((r for r in attempts if r["phase"] == "pre"), None)
        post = next((r for r in attempts if r["phase"] == "post"), None)
        completed = bool(pre and pre["submitted"])
        finished = bool(post and post["submitted"])
        with self.db() as c:
            post_open, post_open_reason, learning_seconds = self.post_access(user["id"], c)
        notice_id = (f"teacher:{self.settings().get('post_updated', '0')}" if post_open_reason == "teacher"
                     else f"time:{AUTO_POST_SECONDS}" if post_open_reason == "time" else None)
        return {"authenticated": True, "role": "student", "student": {"student_no": user["student_no"], "name": user["name"]},
                "pre_completed": completed, "post_completed": finished,
                "post_open": post_open, "post_open_reason": post_open_reason, "post_open_notice_id": notice_id,
                "learning_seconds": round(learning_seconds), "auto_post_seconds": AUTO_POST_SECONDS,
                "auto_post_remaining": max(0, round(AUTO_POST_SECONDS - learning_seconds)),
                "active": next(({"id": r["id"], "phase": r["phase"]} for r in attempts if not r["submitted"]), None),
                "results": [{"phase": r["phase"], "form": r["form"], "started": r["started"], "submitted": r["submitted"],
                             "score": json.loads(r["result"])["score"], "breakdown": json.loads(r["result"])["breakdown"],
                             "sections": section_scores(r)}
                            for r in attempts if r["submitted"]]}

    def start(self, user, phase):
        if is_teacher(user):
            raise HTTPException(403, "教师无需参加学生测验，请在教师管理中查看试卷。")
        with self.db(write=True) as c:
            existing = c.execute("SELECT * FROM attempts WHERE student=? AND phase=?", (user["id"], phase)).fetchone()
            if existing:
                return dict(existing)
            paper_version = VERSION
            if phase == "post":
                pre = c.execute("SELECT submitted, version FROM attempts WHERE student=? AND phase='pre'", (user["id"],)).fetchone()
                if not pre or not pre["submitted"]:
                    raise HTTPException(403, "请先完成前测。")
                if not self.post_access(user["id"], c)[0]:
                    raise HTTPException(403, "后测尚未开放；累计有效学习30分钟后将自动开放，教师也可提前统一开放。")
                paper_version = pre["version"]
            form = user["first_form"] if phase == "pre" else ("B" if user["first_form"] == "A" else "A")
            paper = self.make_paper(form, paper_version)
            ident = secrets.token_hex(16)
            c.execute("INSERT INTO attempts (id,student,phase,form,version,paper,started) VALUES (?,?,?,?,?,?,?)",
                      (ident, user["id"], phase, form, paper["version"], encode(paper), time.time()))
            return dict(c.execute("SELECT * FROM attempts WHERE id=?", (ident,)).fetchone())

    def attempt(self, user, ident, c):
        row = c.execute("SELECT * FROM attempts WHERE id=? AND student=?", (ident, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "测验记录不存在。")
        return dict(row)

    def save(self, user, ident, answers, revision, submit=False):
        with self.db(write=True) as c:
            row = self.attempt(user, ident, c)
            if row["submitted"]:
                if submit:
                    return row
                raise HTTPException(409, "试卷已提交，不能再修改。")
            if revision != row["revision"]:
                raise HTTPException(409, "其他页面已更新作答，请刷新载入最新进度后继续。")
            paper = json.loads(row["paper"])
            allowed = {q["id"]: {o["id"] for o in q["options"]} for q in paper["questions"]}
            if any(k not in allowed or v not in allowed[k] for k, v in answers.items()):
                raise HTTPException(422, "作答包含不属于当前试卷的选项。")
            if submit and set(answers) != set(allowed):
                raise HTTPException(422, f"请完成本卷全部{len(allowed)}个小题后提交。")
            result = None
            if submit:
                breakdown = {}
                sections = {}
                rows = []
                for q in paper["questions"]:
                    earned = q["points"] if answers[q["id"]] == q["correct"] else 0
                    bucket = breakdown.setdefault(q["domain"], {"score": 0, "total": 0})
                    bucket["score"] += earned
                    bucket["total"] += q["points"]
                    key = question_section(q)
                    module = sections.setdefault(key, {"label": SECTION_LABELS[key], "score": 0, "total": 0})
                    module["score"] += earned
                    module["total"] += q["points"]
                    rows.append({"id": q["id"], "pair": q["pair"], "earned": earned, "points": q["points"]})
                result = {"score": sum(r["earned"] for r in rows), "total": paper["total"],
                          "breakdown": breakdown, "sections": sections, "items": rows}
            c.execute("UPDATE attempts SET answers=?, revision=revision+1, submitted=?, result=? WHERE id=?",
                      (encode(answers), time.time() if submit else None, encode(result) if result else None, ident))
            return dict(c.execute("SELECT * FROM attempts WHERE id=?", (ident,)).fetchone())

    def activity(self, user_id, module):
        with self.db(write=True) as c:
            now = time.time()
            c.execute("INSERT INTO activity VALUES (?, ?, 1, ?, ?) ON CONFLICT(student,module) DO UPDATE SET count=count+1,last=excluded.last",
                      (user_id, module, now, now))

    def heartbeat(self, user_id, seconds):
        """Credit foreground learning time while preventing gaps or extra tabs from double counting."""
        now = time.time()
        with self.db(write=True) as c:
            pre = c.execute("SELECT submitted FROM attempts WHERE student=? AND phase='pre'", (user_id,)).fetchone()
            post = c.execute("SELECT submitted FROM attempts WHERE student=? AND phase='post'", (user_id,)).fetchone()
            if not pre or not pre["submitted"] or post:
                return
            row = c.execute("SELECT seconds,last_seen FROM learning_time WHERE student=?", (user_id,)).fetchone()
            if not row:
                c.execute("INSERT INTO learning_time VALUES (?, 0, ?)", (user_id, now))
                return
            elapsed = max(0.0, now - row["last_seen"])
            credit = min(float(seconds), HEARTBEAT_MAX_SECONDS, elapsed + HEARTBEAT_CLOCK_SLOP)
            c.execute("UPDATE learning_time SET seconds=seconds+?,last_seen=? WHERE student=?",
                      (max(0.0, credit), now, user_id))

    def reset_student_state(self, snapshots):
        """Archive the current student view, then start a clean active batch.

        The archive is intentionally stored in the same durable database so the
        faculty view keeps the pre-reset records while students get new state.
        """
        now = time.time()
        reset_id = secrets.token_hex(16)
        with self.db(write=True) as c:
            users = [dict(row) for row in c.execute("SELECT * FROM students") if not is_teacher(row)]
            pairs = {(row["student_no"], row["name"]): row["id"] for row in users}
            for snapshot in snapshots:
                student_id = pairs.get((snapshot["student_no"], snapshot["name"]))
                if not student_id:
                    continue
                c.execute("INSERT INTO study_history (id,reset_at,student_no,name,snapshot) VALUES (?,?,?,?,?)",
                          (secrets.token_hex(16), now, snapshot["student_no"], snapshot["name"], encode(snapshot)))
            student_ids = [row["id"] for row in users]
            if student_ids:
                marks = ",".join("?" for _ in student_ids)
                c.execute(f"DELETE FROM sessions WHERE student IN ({marks})", student_ids)
                c.execute(f"DELETE FROM attempts WHERE student IN ({marks})", student_ids)
                c.execute(f"DELETE FROM activity WHERE student IN ({marks})", student_ids)
                c.execute(f"DELETE FROM learning_time WHERE student IN ({marks})", student_ids)
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rash_quizzes'").fetchone():
                    c.execute(f"DELETE FROM rash_quizzes WHERE student IN ({marks})", student_ids)
                c.execute(f"DELETE FROM students WHERE id IN ({marks})", student_ids)
            c.execute("DELETE FROM login_limits")
        return {"reset_id": reset_id, "reset_at": now, "students": len(users),
                "archived": sum(1 for snapshot in snapshots if (snapshot["student_no"], snapshot["name"]) in pairs)}

    def history_rows(self):
        with self.db() as c:
            rows = [dict(row) for row in c.execute("SELECT reset_at,snapshot FROM study_history ORDER BY reset_at DESC, id DESC")]
        history = []
        for row in rows:
            snapshot = json.loads(row["snapshot"])
            snapshot["history"] = True
            snapshot["reset_at"] = row["reset_at"]
            history.append(snapshot)
        return history


@lru_cache(maxsize=1)
def get_store():
    folder = Path(os.getenv("STUDY_DATA_DIR", str(ROOT / "var")))
    if os.getenv("STUDY_REQUIRE_VOLUME") == "true" and not os.path.ismount(folder):
        raise HTTPException(503, "测验存储尚未就绪，请联系教师。")
    return Store(folder / "study.sqlite3")


def require_student(request: Request):
    user = get_store().user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "请先输入学号和姓名登录。")
    return user


def require_learning(request: Request):
    user = require_student(request)
    if is_teacher(user):
        return user
    rows = get_store().attempts(user["id"])
    if not any(r["phase"] == "pre" and r["submitted"] for r in rows):
        raise HTTPException(403, "请先完成04知识测验中的首次前测。")
    if any(r["phase"] == "post" and not r["submitted"] for r in rows):
        raise HTTPException(403, "后测正在进行，请完成后再返回学习。")
    return user


def faculty(request: Request, x_admin_password: str | None = Header(default=None)):
    if is_teacher(get_store().user(request.cookies.get(COOKIE))):
        return
    password = os.getenv("ADMIN_PASSWORD", "")
    if password and x_admin_password and hmac.compare_digest(password.encode(), x_admin_password.encode()):
        return
    raise HTTPException(401, "请使用教师姓名和学号登录。")


def same_origin(request: Request):
    from urllib.parse import urlsplit
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "不允许跨站提交。")


class Login(BaseModel):
    student_no: str
    name: str


class Answers(BaseModel):
    answers: dict[str, str] = Field(max_length=36)
    revision: int = Field(ge=0)


class Start(BaseModel):
    phase: Literal["pre", "post"]


def public_attempt(row, review=False):
    # Unsubmitted papers never expose keys, even when a caller requests review.
    review = bool(review and row["submitted"])
    paper = json.loads(row["paper"])
    questions = []
    for q in paper["questions"]:
        visible = {k: q[k] for k in ("id", "stem", "options", "points", "case_id")}
        visible["section"] = question_section(q)
        if q.get("image_file"):
            visible.update(image_url=f"/api/assessments/{row['id']}/image/{q['id']}",
                           image_alt="皮疹辨别教学图片")
        if review:
            visible.update({k: q[k] for k in ("correct", "point", "explanation", "sources", "domain")})
            visible["disease"] = q.get("disease", "")
            if q.get("image_source"):
                visible["image_source"] = q["image_source"]
        questions.append(visible)
    return {"id": row["id"], "phase": row["phase"], "form": row["form"], "version": row["version"],
            "started": row["started"], "submitted": row["submitted"], "revision": row["revision"],
            "answers": json.loads(row["answers"]), "questions": questions, "cases": paper["cases"], "total": paper["total"],
            **({"result": {**json.loads(row["result"]), "sections": section_scores(row)}} if review and row["result"] else {})}


def paper_image(paper, question_id):
    q = next((q for q in paper["questions"] if q["id"] == question_id), None)
    filename = q.get("image_file") if q else None
    if not filename or Path(filename).name != filename or not (IMAGE_DIR / filename).is_file():
        raise HTTPException(404, "图片不存在。")
    return FileResponse(IMAGE_DIR / filename, media_type="image/webp", headers={"Cache-Control": "private, no-store"})


@router.post("/api/session/login", dependencies=[Depends(same_origin)])
def login(body: Login, request: Request, response: Response):
    number, name = normalized_identity(body.student_no, body.name)
    if not number or not name or any(unicodedata.category(c).startswith("C") for c in number + name):
        raise HTTPException(422, "请填写姓名和学号，且不要包含控制字符。")
    user, token = get_store().login(number, name, request.client.host if request.client else "unknown")
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https" or os.getenv("STUDY_REQUIRE_VOLUME") == "true", samesite="lax")
    return get_store().status(user)


@router.get("/api/session")
def session(request: Request):
    user = get_store().user(request.cookies.get(COOKIE))
    return get_store().status(user) if user else {"authenticated": False}


@router.post("/api/session/logout", dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    with get_store().db() as c:
        c.execute("DELETE FROM sessions WHERE hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.post("/api/assessments/start", dependencies=[Depends(same_origin)])
def start(body: Start, user=Depends(require_student)):
    return public_attempt(get_store().start(user, body.phase))


@router.get("/api/assessments/{ident}")
def attempt(ident: str, user=Depends(require_student)):
    store = get_store()
    with store.db() as c:
        row = store.attempt(user, ident, c)
    status = store.status(user)
    reviewing_allowed = not (status["active"] and status["active"]["phase"] == "post")
    return public_attempt(row, review=reviewing_allowed)


@router.put("/api/assessments/{ident}/draft", dependencies=[Depends(same_origin)])
def draft(ident: str, body: Answers, user=Depends(require_student)):
    row = get_store().save(user, ident, body.answers, body.revision)
    return {"revision": row["revision"], "saved": True}


@router.get("/api/assessments/{ident}/image/{question_id}")
def assessment_image(ident: str, question_id: str, user=Depends(require_student)):
    store = get_store()
    with store.db() as c:
        row = store.attempt(user, ident, c)
    active = store.status(user)["active"]
    if active and active["phase"] == "post" and row["phase"] != "post":
        raise HTTPException(403, "后测正在进行，完成后可继续查看前测图片。")
    return paper_image(json.loads(row["paper"]), question_id)


@router.post("/api/assessments/{ident}/submit", dependencies=[Depends(same_origin)])
def submit(ident: str, body: Answers, user=Depends(require_student)):
    get_store().save(user, ident, body.answers, body.revision, submit=True)
    return get_store().status(user)


@router.get("/api/assessment-results")
def results(user=Depends(require_student)):
    store = get_store()
    status = store.status(user)
    if status["active"] and status["active"]["phase"] == "post":
        raise HTTPException(403, "后测正在进行，完成后可继续查看解析。")
    completed = [r for r in store.attempts(user["id"]) if r["submitted"]]
    if not completed:
        return {"ready": False}
    return {"ready": True, "attempts": [public_attempt(r, review=True) for r in completed]}


class Visit(BaseModel):
    module: Literal["knowledge", "atlas", "cases"]


@router.post("/api/study/visit", dependencies=[Depends(same_origin)])
def visit(body: Visit, user=Depends(require_learning)):
    if not is_teacher(user):
        get_store().activity(user["id"], body.module)
    return {"ok": True}


class Heartbeat(BaseModel):
    module: Literal["knowledge", "atlas", "cases"]
    seconds: float = Field(ge=0, le=HEARTBEAT_MAX_SECONDS)


@router.post("/api/study/heartbeat", dependencies=[Depends(same_origin)])
def heartbeat(body: Heartbeat, user=Depends(require_learning)):
    if not is_teacher(user):
        get_store().heartbeat(user["id"], body.seconds)
    return get_store().status(user)


class Release(BaseModel):
    open: bool


@router.put("/api/admin/study/release", dependencies=[Depends(faculty), Depends(same_origin)])
def release(body: Release):
    with get_store().db(write=True) as c:
        c.execute("UPDATE settings SET value=? WHERE key='post_open'", ("true" if body.open else "false",))
        c.execute("INSERT OR REPLACE INTO settings VALUES ('post_updated', ?)", (str(time.time()),))
    return {"post_open": body.open}


def faculty_rows():
    store = get_store()
    with store.db() as c:
        users = [dict(r) for r in c.execute("SELECT * FROM students ORDER BY created DESC") if not is_teacher(r)]
        attempts = [dict(r) for r in c.execute("SELECT * FROM attempts")]
        activities = [dict(r) for r in c.execute("SELECT * FROM activity")]
        learning = {r["student"]: dict(r) for r in c.execute("SELECT * FROM learning_time")}
        manual_post_open = c.execute("SELECT value FROM settings WHERE key='post_open'").fetchone()[0] == "true"
    student_ids = {r["id"] for r in users}
    attempts = [r for r in attempts if r["student"] in student_ids]
    rows = []
    for user in users:
        exams = {r["phase"]: r for r in attempts if r["student"] == user["id"]}
        row = {"student_no": user["student_no"], "name": user["name"], "sequence": user["first_form"] + ("B" if user["first_form"] == "A" else "A"),
               "created": user["created"], "activity": {r["module"]: {"visits": r["count"], "first": r["first"], "last": r["last"]} for r in activities if r["student"] == user["id"]}}
        row["learning_seconds"] = round(learning.get(user["id"], {}).get("seconds", 0))
        row["post_access"] = "教师统一开放" if manual_post_open else "学习满30分钟" if row["learning_seconds"] >= AUTO_POST_SECONDS else "未开放"
        for phase in ("pre", "post"):
            r = exams.get(phase)
            row[phase] = ({"status": "已完成" if r["submitted"] else "作答中", "started": r["started"], "submitted": r["submitted"],
                           "form": r["form"], "version": r["version"], "score": json.loads(r["result"])["score"] if r["result"] else None,
                           "sections": section_scores(r)} if r else {"status": "未开始", "score": None})
        a, b = row["pre"]["score"], row["post"]["score"]
        row["gain"] = b-a if a is not None and b is not None else None
        row["interval_hours"] = round((row["post"]["started"] - row["pre"]["submitted"])/3600, 3) if row["post"].get("started") and row["pre"].get("submitted") else None
        rows.append(row)
    return rows, attempts


@router.get("/api/admin/study", dependencies=[Depends(faculty)])
def faculty_summary():
    rows, _ = faculty_rows()
    paired = [r for r in rows if r["gain"] is not None]
    return {"post_open": get_store().settings()["post_open"] == "true", "version": get_store().settings()["version"],
            "students": rows, "registered": len(rows), "pre_completed": sum(r["pre"]["score"] is not None for r in rows),
            "post_completed": len(paired), "mean_gain": round(sum(r["gain"] for r in paired)/len(paired), 2) if paired else None,
            "history": get_store().history_rows()}


@router.post("/api/admin/study/reset", dependencies=[Depends(faculty), Depends(same_origin)])
def reset_student_state():
    rows, _ = faculty_rows()
    return get_store().reset_student_state(rows)


@router.get("/api/admin/study/papers", dependencies=[Depends(faculty)])
def faculty_papers():
    forms = [get_store().make_paper(form) for form in ("A", "B")]
    for paper in forms:
        for q in paper["questions"]:
            if q.pop("image_file", None):
                q["image_url"] = f"/api/admin/study/papers/{paper['form']}/image/{q['id']}"
                q["image_alt"] = "皮疹辨别教学图片"
    return {"version": get_store().settings()["version"], "forms": forms}


@router.get("/api/admin/study/papers/{form}/image/{question_id}", dependencies=[Depends(faculty)])
def faculty_image(form: Literal["A", "B"], question_id: str):
    return paper_image(get_store().make_paper(form), question_id)


@router.get("/api/admin/study/export", dependencies=[Depends(faculty)])
def export(kind: Literal["summary", "items"] = "summary"):
    rows, attempts = faculty_rows()
    data = []
    if kind == "summary":
        header = ["学号", "姓名", "试卷顺序", "前测状态", "前测成绩", "后测状态", "后测成绩", "提升分", "学习间隔小时", "有效学习秒数", "后测开放方式", "知识问答访问次数", "图谱访问次数", "情景访问次数", "前测用时秒", "后测用时秒", "试卷版本"]
        header.extend(f"{phase}{label}{suffix}" for phase in ("前测", "后测") for label in SECTION_LABELS.values() for suffix in ("得分", "满分"))
        for r in rows:
            duration = lambda p: round(r[p]["submitted"]-r[p]["started"]) if r[p].get("submitted") else ""
            data.append([r["student_no"], r["name"], r["sequence"], r["pre"]["status"], r["pre"]["score"], r["post"]["status"], r["post"]["score"], r["gain"], r["interval_hours"], r["learning_seconds"], r["post_access"], *[r["activity"].get(m, {}).get("visits", 0) for m in ("knowledge", "atlas", "cases")], duration("pre"), duration("post"), r["pre"].get("version", get_store().settings()["version"])])
            data[-1].extend(r[p].get("sections", {}).get(key, {}).get(field, "")
                           for p in ("pre", "post") for key in SECTION_LABELS for field in ("score", "total"))
    else:
        header = ["学号", "姓名", "阶段", "卷别", "配对知识点ID", "知识点", "疾病", "难度", "题号", "题干", "所选答案", "正确答案", "得分", "满分", "开始时间戳", "提交时间戳", "版本"]
        header.extend(["测验模块", "题目形式", "图片出处"])
        with get_store().db() as c:
            users = {r["id"]: dict(r) for r in c.execute("SELECT * FROM students")}
        for r in attempts:
            if not r["submitted"]:
                continue
            user = users[r["student"]]
            answers = json.loads(r["answers"])
            for q in json.loads(r["paper"])["questions"]:
                options = {o["id"]: o["text"] for o in q["options"]}
                selected = answers[q["id"]]
                data.append([user["student_no"], user["name"], r["phase"], r["form"], q["pair"], q["point"], q["disease"], q["difficulty"], q["id"], q["stem"], options[selected], options[q["correct"]], q["points"] if selected == q["correct"] else 0, q["points"], r["started"], r["submitted"], r["version"]])
                data[-1].extend([SECTION_LABELS[question_section(q)], "图片题" if q.get("image_file") else "文字题",
                                 q.get("image_source", {}).get("source_label", "")])
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(header)
    for row in data:
        writer.writerow([("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else v) for v in row])
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="study-{kind}.csv"', "Cache-Control": "no-store"})
