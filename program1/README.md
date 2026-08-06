# 互动课堂答题系统

基于 FastAPI + SQLite 的课堂答题数据收集与统计系统：学生端互动课件将答题记录实时上报到后端，教师端看板提供整体统计、错题排行、学生答题明细与名单管理。

## 功能特性

- 学生端互动课件答题上报（单条 / 批量）
- 学生登录与修改密码（默认密码 `88888888`）
- 教师名单管理（上传 / 查看，支持新增、停用、重置密码）
- 统计看板：整体概况、逐题统计、逐学生统计、答题明细
- 后端已配置 CORS（`allow_origins=["*"]`），支持本地 `file://` 直接打开前端页面
- 附带自动化接口测试脚本 `test_api.py`

## 技术栈

| 组件 | 说明 |
| ---- | ---- |
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 数据库 | SQLite + SQLAlchemy 2.x |
| 前端 | 原生 HTML / JavaScript + Tailwind CSS（CDN）+ Chart.js（CDN） |

## 目录结构

```
program1/
├── main.py         # FastAPI 后端入口：全部 API 路由、CORS 配置、学生端页面托管
├── database.py     # SQLite 连接与数据库初始化
├── models.py       # SQLAlchemy 数据模型（AnswerRecord / Student）
├── seed_data.py    # 演示数据脚本：10 条答题记录 + 5 名学生账号（可选执行）
├── teacher.html    # 教师数据看板：统计图表 + 学生明细 + 名单管理
├── 工程材料-材料的性能-互动课堂(莫兰迪)-上报版.html  # 学生端互动课件（答题上报版，由后端 / 托管）
├── 工程材料-材料的性能-互动课堂(莫兰迪).html         # 学生端原始课件（不含上报功能）
├── test_api.py     # 自动化接口测试脚本（requests）
├── requirements.txt # Python 依赖
├── answer_records.db # SQLite 数据库文件（首次启动自动创建）
└── README.md       # 本文档
```

## 快速启动

```bash
# 1. 创建并激活虚拟环境（首次）
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3.（可选）生成演示数据
python seed_data.py

# 4. 启动后端（监听 0.0.0.0:8000，局域网内学生手机可直接访问）
python main.py

# 5. 打开页面
#   学生端：浏览器访问 http://localhost:8000/
#   教师端：浏览器访问 http://localhost:8000/teacher

# 6.（可选）运行自动化接口测试
python test_api.py
```

说明：

- 后端首次启动会自动创建数据表；数据库文件为 `answer_records.db`。
- 学生默认密码为 `88888888`；教师管理口令默认 `teacher888`，可通过环境变量 `ADMIN_KEY` 覆盖后重启生效。
- 学生端与教师端页面中的 API 地址自动取当前站点地址（`window.location.origin`），部署后无需修改代码。
- 学生端页面由后端在根路径 `/` 托管；教师端页面由后端在 `/teacher` 托管。

## API 接口文档

### 通用说明

- Base URL：本地开发为 `http://localhost:8000`，部署后为 `https://你的域名`
- 所有接口均返回 JSON；出错时返回 `{"detail": "错误信息"}` 并附带相应 HTTP 状态码。
- 上传过名单后（名单启用），`/api/answers/*` 只接受名单中且处于启用状态的学生；未上传名单时任意姓名可提交。
- 管理接口需要 `admin_key`（默认 `teacher888`）。

---

### 1. 提交单条答题记录

`POST /api/answers/submit`

请求体：

```json
{
  "student_name": "张三",
  "question_index": 1,
  "question_title": "材料性能-基础：强度的定义",
  "student_answer": "抵抗变形和断裂的能力",
  "correct_answer": "抵抗变形和断裂的能力",
  "is_correct": true,
  "attempt_count": 1
}
```

响应：

```json
{"status": "ok", "id": 1}
```

`id` 为后端自动生成的自增主键；`created_at` 由后端自动填充。

curl 示例：

```bash
curl -X POST http://localhost:8000/api/answers/submit \
  -H "Content-Type: application/json" \
  -d '{"student_name":"张三","question_index":1,"student_answer":"A","correct_answer":"A","is_correct":true,"attempt_count":1}'
```

---

### 2. 批量提交答题记录

`POST /api/answers/batch`

请求体为提交对象的数组（字段同单条提交）：

```json
[
  {
    "student_name": "李四",
    "question_index": 1,
    "question_title": "材料性能-基础：强度的定义",
    "student_answer": "硬度",
    "correct_answer": "抵抗变形和断裂的能力",
    "is_correct": false,
    "attempt_count": 1
  },
  {
    "student_name": "李四",
    "question_index": 2,
    "question_title": "材料性能-基础：塑性测试指标",
    "student_answer": "伸长率",
    "correct_answer": "伸长率",
    "is_correct": true,
    "attempt_count": 1
  }
]
```

响应：

```json
{"status": "ok", "count": 2}
```

---

### 3. 学生登录

`POST /api/auth/login`

请求体：

```json
{"student_name": "张三", "password": "88888888"}
```

响应：

```json
{"status": "ok", "student_name": "张三"}
```

异常：学生不在名单中返回 `404`；密码错误返回 `401`。

---

### 4. 修改密码

`POST /api/auth/change-password`

请求体：

```json
{"student_name": "张三", "old_password": "88888888", "new_password": "123456"}
```

响应：

```json
{"status": "ok"}
```

`new_password` 长度至少 6 位；学生不在名单中返回 `404`，原密码错误返回 `401`。

---

### 5. 上传学生名单（教师）

`POST /api/admin/students`

请求体（`names` 与 `text` 二选一或同时提供）：

```json
{
  "admin_key": "teacher888",
  "names": ["张三", "李四"],
  "text": "王五\n赵六"
}
```

响应：

```json
{
  "status": "ok",
  "created": ["张三", "李四"],
  "reactivated": [],
  "kept": ["王五"],
  "deactivated": ["钱七"],
  "active_count": 4
}
```

行为说明：新学生使用默认密码 `88888888`；重新加入的停用学生密码重置为默认密码；名单内已有学生保留原密码；本次名单之外的学生将被停用（答题记录保留）。管理口令错误返回 `403`。

---

### 6. 查看学生名单（教师）

`GET /api/admin/students?admin_key=teacher888`

响应：

```json
{
  "students": [
    {"name": "张三", "is_active": true},
    {"name": "钱七", "is_active": false}
  ]
}
```

---

### 7. 整体统计

`GET /api/stats/overview`

响应：

```json
{
  "total_students": 3,
  "total_answers": 10,
  "overall_accuracy": 70.0,
  "today_answers": 4
}
```

`overall_accuracy` 为正确率百分比（0~100，保留两位小数）。

---

### 8. 逐题统计

`GET /api/stats/questions`

响应（按错误次数降序排列，同错数按题号升序）：

```json
[
  {
    "question_index": 1,
    "question_title": "材料性能-基础：强度的定义",
    "answer_count": 4,
    "correct_count": 2,
    "error_count": 2,
    "accuracy": 50.0
  }
]
```

---

### 9. 逐学生统计

`GET /api/stats/students`

响应（按正确率降序排列，正确率相同按姓名升序）：

```json
[
  {
    "student_name": "张三",
    "total_answers": 3,
    "correct_count": 3,
    "accuracy": 100.0,
    "attempt_distribution": {"first_attempt": 3},
    "completed_count": 3,
    "total_questions": 4,
    "completion_rate": 75.0
  }
]
```

`attempt_distribution` 的键为 `first_attempt` / `second_attempt` / `third_attempt` / `Nth_attempt`。

---

### 10. 查询学生答题详情

`GET /api/answers/detail?student_name=张三`

响应（按答题时间倒序）：

```json
[
  {
    "id": 1,
    "student_name": "张三",
    "question_index": 1,
    "question_title": "材料性能-基础：强度的定义",
    "student_answer": "抵抗变形和断裂的能力",
    "correct_answer": "抵抗变形和断裂的能力",
    "is_correct": true,
    "attempt_count": 1,
    "created_at": "2026-08-06 17:31:18"
  }
]
```

学生不存在或暂无记录时返回空数组 `[]`。

---

### 其他：学生端首页

`GET /`

返回“上报版”学生端互动课件 HTML 页面，方便局域网内学生直接访问。

## 上线部署

- 代码已支持直接部署：前端 API 同源获取、教师端由 `/teacher` 托管、支持 `HOST`/`PORT` 环境变量。
- 完整步骤见 [DEPLOY.md](DEPLOY.md)：云服务器 + Nginx + HTTPS + 域名备案。

## 自动化测试

```bash
python test_api.py
```

- 默认会自动启动一个临时后端（独立临时数据库），覆盖全部 10 个 API 接口并打印每个用例的 PASS / FAIL，测试结束后自动关闭并清理，不会污染正式的 `answer_records.db`。
- 若 8000 端口已有后端在运行，脚本会拒绝执行；确认要对现有后端测试时使用 `python test_api.py --use-existing`。
- 全部通过时退出码为 0，存在失败为 1，环境错误为 2。

## 常见问题

- **教师端打开后提示“无法连接服务器”**：确认后端已启动（`python main.py`），并通过 `http://localhost:8000/teacher` 打开教师端。
- **学生提交时提示“该学生不在名单中”**：需先在教师端「名单管理」上传包含该学生的名单。
- **忘记学生密码**：教师在「名单管理」重新上传名单即可将学生密码重置为 `88888888`。
- **修改管理口令**：启动后端前设置环境变量 `ADMIN_KEY`，例如 `set ADMIN_KEY=mykey && python main.py`。
