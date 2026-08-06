# main.py
# 学生答题数据收集后端：FastAPI 主应用，包含全部路由

from contextlib import asynccontextmanager
from datetime import date
import hashlib
import os
import re
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db, init_db
from models import AnswerRecord, Student


# 学生端页面（改造后的互动课堂 HTML，服务根路径直接打开）
BASE_DIR = Path(__file__).resolve().parent
STUDENT_PAGE = BASE_DIR / "工程材料-材料的性能-互动课堂(莫兰迪)-上报版.html"

DEFAULT_STUDENT_PASSWORD = "88888888"  # 新加入名单的学生默认密码


# ---------------------------------------------------------------------------
# FastAPI 应用初始化
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """服务启动时自动创建数据库表。"""
    init_db()
    yield


app = FastAPI(
    title="互动课堂答题系统 API",
    description="接收学生答题数据，并提供教师端统计查询接口。",
    version="1.0.0",
    lifespan=lifespan,
)

# 开启 CORS：允许所有来源（前端为本地 HTML 文件，Origin 可能为 null）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 允许所有来源
    allow_credentials=False,  # 通配符与 credentials 组合无效，本地前端无需 Cookie
    allow_methods=["*"],      # 允许所有 HTTP 方法
    allow_headers=["*"],      # 允许所有请求头
)


# ---------------------------------------------------------------------------
# 学生账号 / 登录 / 名单管理工具
# ---------------------------------------------------------------------------

def get_admin_key() -> str:
    """教师管理口令：优先读取环境变量 ADMIN_KEY，否则使用默认值。"""
    return os.environ.get("ADMIN_KEY", "teacher888")


def hash_password(password: str) -> str:
    """PBKDF2-SHA256 加盐哈希，返回 salt$digest 的十六进制串。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def normalize_names(raw_names: list[str]) -> list[str]:
    """把名单文本拆成去重后的姓名列表，兼容换行、逗号、顿号、空格分隔。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_names:
        for part in re.split(r"[\s,，、;；]+", raw or ""):
            name = part.strip()
            if name and name not in seen:
                seen.add(name)
                result.append(name)
    return result


def _roster_enabled(db: Session) -> bool:
    """是否已上传过名单：有名单后，答题上报只接受名单中的学生。"""
    return db.query(func.count(Student.id)).scalar() > 0


def _ensure_allowed_student(db: Session, student_name: str) -> None:
    """有名单时校验学生是否在名单中且处于启用状态。"""
    if not _roster_enabled(db):
        return
    student = db.query(Student).filter(Student.name == student_name.strip()).first()
    if not student or not student.is_active:
        raise HTTPException(status_code=403, detail="该学生不在名单中，无法提交答题记录")


# ---------------------------------------------------------------------------
# 请求体模型
# ---------------------------------------------------------------------------

class AnswerSubmit(BaseModel):
    """单条答题记录的请求体（id 与 created_at 由服务端自动生成）。"""

    student_name: str = Field(..., description="学生姓名")
    question_index: int = Field(..., description="第几题（从 1 开始）")
    question_title: str | None = Field(None, description="题目内容/标题（可选）")
    student_answer: str = Field(..., description="学生的答案")
    correct_answer: str = Field(..., description="正确答案")
    is_correct: bool = Field(..., description="是否正确")
    attempt_count: int = Field(1, ge=1, description="第几次尝试答对（默认 1）")


class LoginRequest(BaseModel):
    """学生登录请求体。"""

    student_name: str = Field(..., min_length=1, max_length=50, description="学生姓名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")


class ChangePasswordRequest(BaseModel):
    """修改密码请求体。"""

    student_name: str = Field(..., min_length=1, max_length=50, description="学生姓名")
    old_password: str = Field(..., min_length=1, max_length=100, description="原密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码（至少 6 位）")


class RosterUploadRequest(BaseModel):
    """教师上传学生名单请求体：names 或 text 二选一。"""

    admin_key: str = Field(..., description="教师管理口令")
    names: list[str] = Field(default_factory=list, description="姓名列表")
    text: str | None = Field(None, description="名单文本（换行/逗号分隔）")


# ---------------------------------------------------------------------------
# 答题数据收集接口
# ---------------------------------------------------------------------------

@app.post("/api/answers/submit")
def submit_answer(payload: AnswerSubmit, db: Session = Depends(get_db)):
    """接收并保存一条答题记录。"""
    _ensure_allowed_student(db, payload.student_name)
    record = AnswerRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"status": "ok", "id": record.id}


@app.post("/api/answers/batch")
def batch_submit(payloads: list[AnswerSubmit], db: Session = Depends(get_db)):
    """批量接收并保存答题记录。"""
    for payload in payloads:
        _ensure_allowed_student(db, payload.student_name)
    records = [AnswerRecord(**p.model_dump()) for p in payloads]
    db.add_all(records)
    db.commit()
    return {"status": "ok", "count": len(records)}


# ---------------------------------------------------------------------------
# 登录 / 修改密码 / 名单管理接口
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """学生登录：姓名必须在名单中且密码正确。"""
    student = db.query(Student).filter(Student.name == payload.student_name.strip()).first()
    if not student or not student.is_active:
        raise HTTPException(status_code=404, detail="名单中没有该学生，请联系老师")
    if not verify_password(payload.password, student.password_hash):
        raise HTTPException(status_code=401, detail="密码错误")
    return {"status": "ok", "student_name": student.name}


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    """学生修改自己的密码：需校验原密码。"""
    student = db.query(Student).filter(Student.name == payload.student_name.strip()).first()
    if not student or not student.is_active:
        raise HTTPException(status_code=404, detail="名单中没有该学生")
    if not verify_password(payload.old_password, student.password_hash):
        raise HTTPException(status_code=401, detail="原密码错误")
    student.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


@app.post("/api/admin/students")
def upload_roster(payload: RosterUploadRequest, db: Session = Depends(get_db)):
    """教师上传学生名单：新学生默认密码 88888888；已停用学生重新加入时重置为默认密码；
    已在名单中的学生保留原密码；不在本次名单中的学生将被停用（答题记录保留）。"""
    if payload.admin_key != get_admin_key():
        raise HTTPException(status_code=403, detail="管理口令错误")

    names = normalize_names(payload.names + ([payload.text] if payload.text else []))
    if not names:
        raise HTTPException(status_code=400, detail="名单为空，请至少输入一个姓名")

    created: list[str] = []      # 新加入（默认密码）
    reactivated: list[str] = []  # 之前被停用、本次重新加入（密码重置为默认）
    kept: list[str] = []         # 已在名单中（保留原密码）

    for name in names:
        student = db.query(Student).filter(Student.name == name).first()
        if student is None:
            db.add(Student(name=name, password_hash=hash_password(DEFAULT_STUDENT_PASSWORD), is_active=True))
            created.append(name)
        elif not student.is_active:
            student.is_active = True
            student.password_hash = hash_password(DEFAULT_STUDENT_PASSWORD)
            reactivated.append(name)
        else:
            kept.append(name)

    name_set = set(names)
    deactivated: list[str] = []
    for student in db.query(Student).filter(Student.is_active.is_(True)).all():
        if student.name not in name_set:
            student.is_active = False
            deactivated.append(student.name)

    db.commit()
    return {
        "status": "ok",
        "created": created,
        "reactivated": reactivated,
        "kept": kept,
        "deactivated": deactivated,
        "active_count": len(names),
    }


@app.get("/api/admin/students")
def list_students(admin_key: str, db: Session = Depends(get_db)):
    """教师查看当前名单（含停用学生）。"""
    if admin_key != get_admin_key():
        raise HTTPException(status_code=403, detail="管理口令错误")
    rows = db.query(Student).order_by(Student.id).all()
    return {"students": [{"name": s.name, "is_active": s.is_active} for s in rows]}


# ---------------------------------------------------------------------------
# 统计查询接口
# ---------------------------------------------------------------------------

def _safe_accuracy(correct: int, total: int) -> float:
    """计算正确率（百分比，0~100，保留 2 位小数），避免除零。"""
    return round(correct / total * 100, 2) if total else 0.0


def _attempt_key(attempt_count: int) -> str:
    """把尝试次数转换为分布键名，如 1->first_attempt、2->second_attempt。"""
    names = {1: "first_attempt", 2: "second_attempt", 3: "third_attempt"}
    return names.get(attempt_count, f"{attempt_count}th_attempt")


@app.get("/api/stats/overview")
def stats_overview(db: Session = Depends(get_db)):
    """总体统计：总答题人数、总答题次数、整体正确率、今日答题数。"""
    total_students = db.query(func.count(func.distinct(AnswerRecord.student_name))).scalar() or 0
    total_answers = db.query(func.count(AnswerRecord.id)).scalar() or 0
    correct_answers = (
        db.query(func.count(AnswerRecord.id))
        .filter(AnswerRecord.is_correct.is_(True))
        .scalar()
        or 0
    )
    today_answers = (
        db.query(func.count(AnswerRecord.id))
        .filter(func.date(AnswerRecord.created_at) == date.today().isoformat())
        .scalar()
        or 0
    )
    return {
        "total_students": total_students,
        "total_answers": total_answers,
        "overall_accuracy": _safe_accuracy(correct_answers, total_answers),
        "today_answers": today_answers,
    }


@app.get("/api/stats/questions")
def stats_questions(db: Session = Depends(get_db)):
    """每道题的统计：题目索引、正确率、答题次数、错误次数；按错误次数降序排列。"""
    records = (
        db.query(AnswerRecord)
        .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
        .all()
    )
    groups: dict[int, dict] = {}
    for r in records:
        g = groups.setdefault(
            r.question_index,
            {
                "question_index": r.question_index,
                "question_title": None,
                "answer_count": 0,
                "correct_count": 0,
                "error_count": 0,
            },
        )
        g["answer_count"] += 1
        if r.is_correct:
            g["correct_count"] += 1
        else:
            g["error_count"] += 1
        # 取该题最近一条非空标题
        if r.question_title and g["question_title"] is None:
            g["question_title"] = r.question_title

    result = [
        {**g, "accuracy": _safe_accuracy(g["correct_count"], g["answer_count"])}
        for g in groups.values()
    ]
    # 按错误次数降序，同错数按题号升序
    result.sort(key=lambda x: (-x["error_count"], x["question_index"]))
    return result


@app.get("/api/stats/students")
def stats_students(db: Session = Depends(get_db)):
    """每个学生的统计：姓名、总答题数、正确数、正确率、答题次数分布、完成情况；按正确率降序。"""
    records = db.query(AnswerRecord).all()
    # 库中所有不同题目数（用于计算完成率）
    total_questions = len({r.question_index for r in records})

    students: dict[str, dict] = {}
    for r in records:
        s = students.setdefault(
            r.student_name,
            {
                "student_name": r.student_name,
                "total_answers": 0,
                "correct_count": 0,
                "attempt_distribution": {},
                "completed_questions": set(),
            },
        )
        s["total_answers"] += 1
        if r.is_correct:
            s["correct_count"] += 1
            key = _attempt_key(r.attempt_count)
            s["attempt_distribution"][key] = s["attempt_distribution"].get(key, 0) + 1
        s["completed_questions"].add(r.question_index)

    result = []
    for s in students.values():
        accuracy = _safe_accuracy(s["correct_count"], s["total_answers"])
        completed = len(s["completed_questions"])
        result.append(
            {
                "student_name": s["student_name"],
                "total_answers": s["total_answers"],
                "correct_count": s["correct_count"],
                "accuracy": accuracy,
                "attempt_distribution": s["attempt_distribution"],
                "completed_count": completed,
                "total_questions": total_questions,
                "completion_rate": _safe_accuracy(completed, total_questions),
            }
        )
    # 固定按正确率降序排列（正确率相同时按姓名升序，保证顺序稳定）
    result.sort(key=lambda x: (-x["accuracy"], x["student_name"]))
    return result


@app.get("/api/answers/detail")
def answers_detail(student_name: str, db: Session = Depends(get_db)):
    """返回某个学生的所有答题明细，按答题时间倒序。"""
    records = (
        db.query(AnswerRecord)
        .filter(AnswerRecord.student_name == student_name)
        .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "student_name": r.student_name,
            "question_index": r.question_index,
            "question_title": r.question_title,
            "student_answer": r.student_answer,
            "correct_answer": r.correct_answer,
            "is_correct": r.is_correct,
            "attempt_count": r.attempt_count,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds"),
        }
        for r in records
    ]


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    """直接在根路径提供学生端互动课堂页面，方便局域网内学生手机访问。"""
    return FileResponse(STUDENT_PAGE, media_type="text/html")


@app.get("/teacher", include_in_schema=False)
def teacher_page():
    """在 /teacher 路径托管教师端数据看板页面。"""
    return FileResponse(BASE_DIR / "teacher.html", media_type="text/html")


if __name__ == "__main__":
    # 启动服务：默认端口 8000，监听 0.0.0.0；可通过环境变量 HOST / PORT 覆盖
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
    from fastapi.responses import HTMLResponse
import os

# 读取HTML文件的通用函数
def load_html(filename: str) -> str:
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, filename)
        print(f"[DEBUG] 尝试加载文件: {file_path}")  # ← 加这一行
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"[ERROR] 文件未找到: {file_path}")  # ← 加这一行
        return "<h1>❌ 页面未找到，请检查HTML文件是否已上传到项目根目录</h1>"
    except Exception as e:
        print(f"[ERROR] 加载失败: {str(e)}")  # ← 加这一行
        return f"<h1>❌ 加载页面失败: {str(e)}</h1>"

# 学生端首页
@app.get("/", response_class=HTMLResponse)
async def serve_student():
    return load_html("工程材料-材料的性能-互动课堂(莫兰迪)-上报版.html")

# 教师端（带口令验证）
@app.get("/teacher", response_class=HTMLResponse)
async def serve_teacher(key: str = ""):
    admin_key = os.getenv("ADMIN_KEY")
    if not admin_key:
        return "<h2>⚠️ 服务端未配置ADMIN_KEY环境变量，请联系管理员</h2>"
    if key != admin_key:
        return "<h2>🔒 管理员口令错误，请重新输入</h2>"
    return load_html("teacher.html")
