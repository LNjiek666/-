# models.py
# SQLAlchemy 数据模型定义

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from database import Base


class AnswerRecord(Base):
    """一条学生答题记录。"""

    __tablename__ = "answer_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # 自增主键
    student_name = Column(String(50), nullable=False, index=True)  # 学生姓名
    question_index = Column(Integer, nullable=False, index=True)  # 第几题（从 1 开始）
    question_title = Column(String(200), nullable=True)  # 题目内容/标题（可选）
    student_answer = Column(String(500), nullable=False)  # 学生的答案
    correct_answer = Column(String(500), nullable=False)  # 正确答案
    is_correct = Column(Boolean, nullable=False, default=False)  # 是否正确
    attempt_count = Column(Integer, nullable=False, default=1)  # 第几次尝试答对（默认 1）
    created_at = Column(DateTime, nullable=False, default=datetime.now)  # 答题时间（本地时间，自动填充）


class Student(Base):
    """学生账号：名单中的学生才能登录答题。"""

    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)  # 自增主键
    name = Column(String(50), nullable=False, unique=True, index=True)  # 姓名（唯一）
    password_hash = Column(String(200), nullable=False)  # PBKDF2 加盐哈希（salt$digest 十六进制）
    is_active = Column(Boolean, nullable=False, default=True)  # 是否在名单中（False 表示已停用）
    created_at = Column(DateTime, nullable=False, default=datetime.now)  # 创建时间
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)  # 更新时间


class ProgressRecord(Base):
    """学生完成进度：每个学生每一节一条完成记录（学生端「标记本节完成」上报）。"""

    __tablename__ = "progress_records"
    __table_args__ = (
        UniqueConstraint("student_name", "scene_index", name="uq_progress_student_scene"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_name = Column(String(50), nullable=False, index=True)
    scene_index = Column(Integer, nullable=False, index=True)  # 第几节（从 0 开始）
    total_scenes = Column(Integer, nullable=False, default=0)  # 课程总节数
    completed_at = Column(DateTime, nullable=False, default=datetime.now)  # 完成时间
