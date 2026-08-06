# seed_data.py
# 生成 10 条模拟答题数据，方便测试
# 用法：
#   python seed_data.py          # 已有数据时跳过
#   python seed_data.py --reset  # 清空后重新生成

import sys

from sqlalchemy import func

from database import SessionLocal, init_db
from main import DEFAULT_STUDENT_PASSWORD, hash_password
from models import AnswerRecord, Student

# 演示学生账号（与 10 条答题记录中的学生一致）
DEMO_STUDENTS = ["张三", "李四", "王五", "赵六", "钱七"]


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
    """插入 10 条模拟数据并确保演示学生账号存在；已有数据时默认跳过。"""
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

        # (学生姓名, 题号, 题目标题, 学生答案, 正确答案, 是否正确, 尝试次数)
        mock_data = [
            ("张三", 1, "材料性能-基础：强度的定义", "抵抗变形和断裂的能力", "抵抗变形和断裂的能力", True, 1),
            ("张三", 2, "材料性能-基础：塑性测试指标", "伸长率", "伸长率", True, 1),
            ("李四", 1, "材料性能-基础：强度的定义", "硬度", "抵抗变形和断裂的能力", False, 1),
            ("李四", 1, "材料性能-基础：强度的定义", "抵抗变形和断裂的能力", "抵抗变形和断裂的能力", True, 2),
            ("王五", 3, "材料性能-基础：刚度提高手段", "增大截面尺寸", "增大截面尺寸", False, 1),
            ("王五", 4, "材料性能-应用：拉伸试验结果", "强度、塑性", "强度、塑性", True, 1),
            ("赵六", 5, "材料性能-应用：硬度测试选择", "洛氏硬度", "洛氏硬度", True, 1),
            ("赵六", 6, "材料性能-应用：疲劳失效特征", "河流花样", "疲劳辉纹", False, 1),
            ("钱七", 7, "材料性能-综合：锻造性能", "塑性", "塑性", True, 1),
            ("钱七", 8, "材料性能-综合：焊接性因素", "低碳钢", "低碳钢", True, 1),
        ]

        for name, qidx, title, ans, correct, ok, attempt in mock_data:
            db.add(
                AnswerRecord(
                    student_name=name,
                    question_index=qidx,
                    question_title=title,
                    student_answer=ans,
                    correct_answer=correct,
                    is_correct=ok,
                    attempt_count=attempt,
                )
            )
        db.commit()
        print(f"已生成 {len(mock_data)} 条模拟答题数据。")
    finally:
        db.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
