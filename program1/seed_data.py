# seed_data.py
# 基于学生端课程目录（随堂测验）生成模拟答题数据，方便测试
# 用法：
#   python seed_data.py          # 已有数据时跳过
#   python seed_data.py --reset  # 清空后重新生成

import sys

from sqlalchemy import func

from course_catalog import load_course_catalog
from database import SessionLocal, init_db
from main import DEFAULT_STUDENT_PASSWORD, hash_password
from models import AnswerRecord, Student

# 演示学生账号（与答题记录中的学生一致）
DEMO_STUDENTS = ["张三", "李四", "王五", "赵六", "钱七"]

# 演示剧本：(学生, 课程目录中小节序号, 题号, 是否正确, 尝试次数)
# 覆盖多个小节，部分题目无人作答，并包含重复作答以验证“每题每生取最后一次”的统计口径。
DEMO_SCRIPT = [
    # 第 2 节 随堂测验：强度与塑性（目录序号 0）
    ("张三", 0, 0, True, 1),
    ("李四", 0, 0, False, 1), ("李四", 0, 0, True, 2),  # 李四第一次答错、第二次答对
    ("王五", 0, 0, True, 1),
    ("张三", 0, 1, True, 1), ("李四", 0, 1, False, 1),
    ("王五", 0, 1, True, 1), ("赵六", 0, 1, False, 1),
    ("张三", 0, 2, True, 1), ("李四", 0, 2, True, 1),
    # 第 3 节 随堂测验：硬度（目录序号 1）
    ("张三", 1, 0, True, 1), ("李四", 1, 0, True, 1), ("王五", 1, 0, False, 1),
    ("张三", 1, 1, True, 1), ("王五", 1, 1, True, 1),
    ("李四", 1, 2, False, 1),
    # 第 4 节 随堂测验：韧性与疲劳强度（目录序号 2）
    ("张三", 2, 0, True, 1), ("赵六", 2, 0, True, 1), ("钱七", 2, 0, False, 1),
    ("钱七", 2, 1, True, 1),
    # 第 5 节 随堂测验：工艺性能（目录序号 3）
    ("张三", 3, 0, True, 1), ("李四", 3, 0, True, 1), ("王五", 3, 0, True, 1),
    ("赵六", 3, 1, True, 1), ("钱七", 3, 1, False, 1),
]


def _build_demo_records() -> list[dict]:
    """根据课程目录与演示剧本生成答题记录（含小节信息）。"""
    catalog = load_course_catalog()
    if not catalog["scenes"]:
        return []
    records: list[dict] = []
    for student, scene_ord, qidx, correct, attempt in DEMO_SCRIPT:
        scene = catalog["scenes"][scene_ord]
        q = scene["questions"][qidx]
        records.append(
            {
                "student_name": student,
                "scene_index": scene["scene_index"],
                "scene_title": scene["scene_title"],
                "question_index": q["question_index"],
                "question_title": q["question_title"],
                "student_answer": q["correct_answer"] if correct else "错误作答（演示数据）",
                "correct_answer": q["correct_answer"],
                "is_correct": correct,
                "attempt_count": attempt,
            }
        )
    return records


def _ensure_students(db) -> list[str]:
    """确保演示学生账号存在（默认密码），返回本次新建的姓名列表。"""
    existing = {s.name for s in db.query(Student).all()}
    created = []
    for name in DEMO_STUDENTS:
        if name not in existing:
            db.add(
                Student(
                    name=name,
                    password_hash=hash_password(DEFAULT_STUDENT_PASSWORD),
                    is_active=True,
                )
            )
            created.append(name)
    return created


def seed(reset: bool = False) -> None:
    """插入演示答题数据并确保演示学生账号存在；已有数据时默认跳过。"""
    init_db()
    db = SessionLocal()
    try:
        existing_answers = db.query(func.count(AnswerRecord.id)).scalar() or 0
        if reset:
            print("检测到 --reset，将清空现有答题记录与学生账号后重新生成。")
            db.query(AnswerRecord).delete()
            db.query(Student).delete()
            existing_answers = 0
        elif existing_answers:
            print(
                f"数据库中已有 {existing_answers} 条答题记录，跳过答题数据生成"
                "（如需重新生成请加 --reset 参数）。"
            )

        # 无论是否跳过答题数据，都确保演示学生账号存在
        created_students = _ensure_students(db)
        if created_students:
            print(
                f"已创建学生账号：{'、'.join(created_students)}"
                f"（默认密码 {DEFAULT_STUDENT_PASSWORD}）。"
            )
        else:
            print(f"学生账号已存在（默认密码 {DEFAULT_STUDENT_PASSWORD}），无需重复创建。")

        if existing_answers and not reset:
            db.commit()
            return

        mock_data = _build_demo_records()
        for rec in mock_data:
            db.add(
                AnswerRecord(
                    student_name=rec["student_name"],
                    scene_index=rec["scene_index"],
                    scene_title=rec["scene_title"],
                    question_index=rec["question_index"],
                    question_title=rec["question_title"],
                    student_answer=rec["student_answer"],
                    correct_answer=rec["correct_answer"],
                    is_correct=rec["is_correct"],
                    attempt_count=rec["attempt_count"],
                )
            )
        db.commit()
        print(f"已生成 {len(mock_data)} 条模拟答题数据。")
    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
