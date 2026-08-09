# database.py
# 数据库连接配置：SQLite + SQLAlchemy ORM

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite 数据库文件存放在项目根目录
SQLALCHEMY_DATABASE_URL = "sqlite:///./answer_records.db"

# 创建数据库引擎；SQLite 需要 check_same_thread=False 以支持 FastAPI 多线程访问
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 模型基类
Base = declarative_base()


def get_db():
    """FastAPI 依赖：为每个请求提供一个数据库会话，用完自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有尚未存在的表（启动时自动调用），并补充新列。"""
    import models  # 导入模型，确保表结构注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns():
    """SQLite 轻量迁移：为已存在的 answer_records 表补充新列（幂等，可重复执行）。"""
    from sqlalchemy import text

    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(answer_records)"))}
        if "scene_index" not in cols:
            conn.execute(text("ALTER TABLE answer_records ADD COLUMN scene_index INTEGER"))
        if "scene_title" not in cols:
            conn.execute(text("ALTER TABLE answer_records ADD COLUMN scene_title VARCHAR(200)"))
