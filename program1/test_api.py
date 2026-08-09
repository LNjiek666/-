# -*- coding: utf-8 -*-
"""互动课堂答题系统 - 自动化接口测试脚本

覆盖后端全部 API 的正常响应，并打印每个用例的通过 / 失败状态。

用法：
    python test_api.py                  # 自动启动临时后端（独立临时数据库），测试结束自动关闭并清理
    python test_api.py --use-existing   # 使用已运行在 http://localhost:8000 的后端（会写入其真实数据库）

退出码：0 全部通过；1 存在失败；2 环境错误（端口被占用 / 后端不可用）。
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"
PROJECT_DIR = Path(__file__).resolve().parent

ADMIN_KEY = "teacher888"  # 与 main.py 的默认管理口令一致
DEFAULT_PWD = "88888888"  # 学生默认密码
NEW_PWD = "abc123456"

STUDENT_1, STUDENT_2, STUDENT_3 = "张三", "李四", "王五"

passed: list[str] = []
failed: list[str] = []


def api(method: str, path: str, **kwargs) -> requests.Response:
    """发送请求到测试后端。"""
    return requests.request(method, BASE_URL + path, timeout=10, **kwargs)


def run_test(name: str, fn) -> None:
    """执行一个用例：通过记录 PASS，失败 / 异常记录 FAIL。"""
    try:
        detail = fn()
        passed.append(name)
        print(f"[PASS] {name}" + (f" | {detail}" if detail else ""))
    except Exception as exc:
        failed.append(name)
        print(f"[FAIL] {name} | {type(exc).__name__}: {exc}")


def expect(resp: requests.Response, status: int, what: str = "") -> dict:
    """断言 HTTP 状态码并返回 JSON 响应体。"""
    assert resp.status_code == status, (
        f"{what}期望 HTTP {status}，实际 {resp.status_code}，响应：{resp.text[:300]}"
    )
    try:
        return resp.json()
    except ValueError:
        raise AssertionError(f"{what}响应不是合法 JSON：{resp.text[:200]}")


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_root_page():
    resp = api("GET", "/")
    assert resp.status_code == 200, f"学生端首页应返回 200，实际 {resp.status_code}"
    assert "text/html" in resp.headers.get("content-type", ""), "学生端首页应为 text/html"
    return f"content-type={resp.headers.get('content-type')}"


def test_upload_roster():
    body = {"admin_key": ADMIN_KEY, "names": [STUDENT_1, STUDENT_2, STUDENT_3]}
    data = expect(api("POST", "/api/admin/students", json=body), 200, "上传名单")
    assert data.get("status") == "ok", f"status 应为 ok，实际 {data}"
    assert data.get("created") == [STUDENT_1, STUDENT_2, STUDENT_3], f"应新建 3 人，实际 {data}"
    assert data.get("active_count") == 3, f"active_count 应为 3，实际 {data}"
    return f"created={data['created']}, active_count={data['active_count']}"


def test_upload_roster_wrong_key():
    body = {"admin_key": "wrong-key", "names": ["张三"]}
    expect(api("POST", "/api/admin/students", json=body), 403, "错误口令上传名单")
    return "返回 403"


def test_list_students():
    data = expect(api("GET", "/api/admin/students", params={"admin_key": ADMIN_KEY}), 200, "查看名单")
    names = [s["name"] for s in data.get("students", [])]
    assert names == [STUDENT_1, STUDENT_2, STUDENT_3], f"名单应为 3 人，实际 {names}"
    return f"students={names}"


def test_login_ok():
    data = expect(
        api("POST", "/api/auth/login", json={"student_name": STUDENT_1, "password": DEFAULT_PWD}),
        200, "学生登录",
    )
    assert data.get("student_name") == STUDENT_1, f"student_name 应为 {STUDENT_1}，实际 {data}"
    return f"student_name={data['student_name']}"


def test_login_wrong_password():
    expect(
        api("POST", "/api/auth/login", json={"student_name": STUDENT_1, "password": "bad"}),
        401, "错误密码登录",
    )
    return "返回 401"


def test_login_not_in_roster():
    expect(
        api("POST", "/api/auth/login", json={"student_name": "赵六", "password": DEFAULT_PWD}),
        404, "名单外学生登录",
    )
    return "返回 404"


def test_change_password():
    body = {"student_name": STUDENT_1, "old_password": DEFAULT_PWD, "new_password": NEW_PWD}
    data = expect(api("POST", "/api/auth/change-password", json=body), 200, "修改密码")
    assert data.get("status") == "ok", f"status 应为 ok，实际 {data}"
    data = expect(
        api("POST", "/api/auth/login", json={"student_name": STUDENT_1, "password": NEW_PWD}),
        200, "新密码登录",
    )
    assert data.get("student_name") == STUDENT_1
    return "新密码登录成功"


def test_submit_single():
    body = {
        "student_name": STUDENT_1,
        "question_index": 1,
        "question_title": "材料性能-基础：强度的定义",
        "student_answer": "抵抗变形和断裂的能力",
        "correct_answer": "抵抗变形和断裂的能力",
        "is_correct": True,
        "attempt_count": 1,
    }
    data = expect(api("POST", "/api/answers/submit", json=body), 200, "单条提交")
    assert data.get("status") == "ok", f"status 应为 ok，实际 {data}"
    assert isinstance(data.get("id"), int), f"应返回自增 id，实际 {data}"
    return f"id={data['id']}"


def test_submit_with_scene():
    # 用课程目录中的真实题目提交（含小节信息），并模拟李四“先答错、再改对”
    from course_catalog import load_course_catalog

    scene = load_course_catalog()["scenes"][0]  # 第 2 节 随堂测验：强度与塑性
    q = scene["questions"][0]
    base = {
        "scene_index": scene["scene_index"],
        "scene_title": scene["scene_title"],
        "question_index": q["question_index"],
        "question_title": q["question_title"],
        "correct_answer": q["correct_answer"],
    }
    payload = {**base, "student_name": STUDENT_3, "student_answer": q["correct_answer"],
               "is_correct": True, "attempt_count": 1}
    expect(api("POST", "/api/answers/submit", json=payload), 200, "带小节信息提交")
    payload = {**base, "student_name": STUDENT_2, "student_answer": "错误作答（演示）",
               "is_correct": False, "attempt_count": 1}
    expect(api("POST", "/api/answers/submit", json=payload), 200, "带小节信息提交（答错）")
    payload = {**base, "student_name": STUDENT_2, "student_answer": q["correct_answer"],
               "is_correct": True, "attempt_count": 2}
    expect(api("POST", "/api/answers/submit", json=payload), 200, "带小节信息重复提交")
    return f"scene_index={scene['scene_index']}, question_index={q['question_index']}"


def test_submit_not_in_roster():
    body = {
        "student_name": "未知学生",
        "question_index": 1,
        "student_answer": "x",
        "correct_answer": "y",
        "is_correct": False,
        "attempt_count": 1,
    }
    expect(api("POST", "/api/answers/submit", json=body), 403, "名单外学生提交")
    return "返回 403"


def test_batch_submit():
    payloads = [
        {"student_name": STUDENT_2, "question_index": 1, "question_title": "材料性能-基础：强度的定义",
         "student_answer": "硬度", "correct_answer": "抵抗变形和断裂的能力", "is_correct": False, "attempt_count": 1},
        {"student_name": STUDENT_2, "question_index": 2, "question_title": "材料性能-基础：塑性测试指标",
         "student_answer": "伸长率", "correct_answer": "伸长率", "is_correct": True, "attempt_count": 1},
        {"student_name": STUDENT_3, "question_index": 3, "question_title": "材料性能-基础：刚度提高手段",
         "student_answer": "增大截面尺寸", "correct_answer": "增大截面尺寸", "is_correct": True, "attempt_count": 1},
    ]
    data = expect(api("POST", "/api/answers/batch", json=payloads), 200, "批量提交")
    assert data.get("status") == "ok" and data.get("count") == 3, f"应提交 3 条，实际 {data}"
    return f"count={data['count']}"


def test_batch_empty():
    data = expect(api("POST", "/api/answers/batch", json=[]), 200, "空批量提交")
    assert data.get("count") == 0, f"空数组应返回 count=0，实际 {data}"
    return "count=0"


def test_stats_overview():
    data = expect(api("GET", "/api/stats/overview"), 200, "整体统计")
    assert data["total_students"] == 3, f"答题学生数应为 3，实际 {data}"
    assert data["total_answers"] == 7, f"答题总数应为 7（1 单条 + 3 带小节 + 3 批量），实际 {data}"
    assert data["overall_accuracy"] == 71.43, f"整体正确率应为 71.43，实际 {data}"
    assert data["today_answers"] == 7, f"今日答题数应为 7，实际 {data}"
    return json.dumps(data, ensure_ascii=False)


def test_stats_questions():
    data = expect(api("GET", "/api/stats/questions"), 200, "逐题统计")
    assert isinstance(data, list) and len(data) == 4, f"应有 4 道题，实际 {data}"
    assert data[0]["question_index"] == 0, f"错误次数最多的应排第一（第 0 题），实际 {data}"
    q1 = next(q for q in data if q["question_index"] == 1)
    assert q1["answer_count"] == 2 and q1["error_count"] == 1 and q1["accuracy"] == 50.0, f"第 1 题统计错误，实际 {q1}"
    return json.dumps(data, ensure_ascii=False)


def test_stats_question_groups():
    data = expect(api("GET", "/api/stats/question-groups"), 200, "分小节题目统计")
    scenes = data.get("scenes", [])
    assert len(scenes) == 5, f"应有 4 个测验小节 + 1 个未分类，实际 {len(scenes)}"
    by_idx = {s.get("scene_index"): s for s in scenes}
    s2 = by_idx.get(2)
    assert s2 and s2["scene_title"].startswith("第 2 节"), f"应包含第 2 节测验，实际 {s2}"
    assert len(s2["questions"]) == 5, f"第 2 节测验应列出全部 5 道题，实际 {len(s2['questions'])}"
    q0 = s2["questions"][0]
    assert q0["answer_count"] == 2, f"每题每生去重后应为 2 人作答，实际 {q0}"
    assert q0["correct_count"] == 2 and q0["error_count"] == 0, f"李四改对后应记为正确，实际 {q0}"
    assert q0["accuracy"] == 100.0, f"正确率应为 100.0，实际 {q0}"
    assert q0["correct_answer"], "应返回正确答案"
    uncat = next((s for s in scenes if s.get("scene_index") is None), None)
    assert uncat and uncat["scene_title"] == "未分类", "应包含未分类分组"
    assert len(uncat["questions"]) == 3, f"未分类应为 3 道旧题目，实际 {len(uncat['questions'])}"
    return f"scenes={len(scenes)}, scene2_q0={json.dumps(q0, ensure_ascii=False)}"


def test_stats_students():
    data = expect(api("GET", "/api/stats/students"), 200, "逐学生统计")
    assert isinstance(data, list) and len(data) == 3, f"应有 3 名学生，实际 {data}"
    acc = {s["student_name"]: s["accuracy"] for s in data}
    assert acc[STUDENT_1] == 100.0 and acc[STUDENT_2] == 50.0 and acc[STUDENT_3] == 100.0, f"正确率不符，实际 {acc}"
    acc_list = [s["accuracy"] for s in data]
    assert acc_list == sorted(acc_list, reverse=True), "应按正确率降序排列"
    return json.dumps(data, ensure_ascii=False)


def test_answer_detail():
    data = expect(api("GET", "/api/answers/detail", params={"student_name": STUDENT_1}), 200, "学生答题详情")
    assert isinstance(data, list) and len(data) == 1, f"{STUDENT_1} 应有 1 条记录，实际 {data}"
    fields = {"id", "student_name", "question_index", "student_answer", "correct_answer",
              "is_correct", "attempt_count", "created_at"}
    assert fields.issubset(data[0].keys()), f"明细字段缺失，实际 {data[0].keys()}"
    return json.dumps(data, ensure_ascii=False)


def test_answer_detail_unknown():
    data = expect(api("GET", "/api/answers/detail", params={"student_name": "不存在"}), 200, "未知学生明细")
    assert data == [], f"未知学生应返回空数组，实际 {data}"
    return "返回 []"


def test_progress_mark():
    data = expect(api("POST", "/api/progress/mark", json={
        "student_name": STUDENT_1, "scene_index": 0, "total_scenes": 10, "completed": True,
    }), 200, "标记第 1 节完成")
    assert data.get("completed") is True, f"completed 应为 True，实际 {data}"
    data = expect(api("POST", "/api/progress/mark", json={
        "student_name": STUDENT_1, "scene_index": 1, "total_scenes": 10, "completed": True,
    }), 200, "标记第 2 节完成")
    assert data.get("scene_index") == 1, f"scene_index 应为 1，实际 {data}"
    return f"scene_index={data['scene_index']}"


def test_progress_sync():
    data = expect(api("POST", "/api/progress/sync", json={
        "student_name": STUDENT_2, "total_scenes": 10, "completed_scenes": [0, 1, 2],
    }), 200, "全量同步进度")
    assert data.get("synced") == 3, f"应同步 3 节，实际 {data}"
    return f"synced={data['synced']}"


def test_progress_stats():
    data = expect(api("GET", "/api/stats/progress"), 200, "进度统计")
    assert data.get("total_scenes") == 10, f"总节数应为 10，实际 {data}"
    by_name = {s["student_name"]: s for s in data.get("students", [])}
    assert by_name[STUDENT_1]["completed_count"] == 2, f"{STUDENT_1} 应完成 2 节，实际 {by_name[STUDENT_1]}"
    assert by_name[STUDENT_2]["completed_count"] == 3, f"{STUDENT_2} 应完成 3 节，实际 {by_name[STUDENT_2]}"
    assert by_name[STUDENT_3]["completed_count"] == 0, f"{STUDENT_3} 应完成 0 节，实际 {by_name[STUDENT_3]}"
    assert by_name[STUDENT_1]["completion_rate"] == 20.0, f"完成率应为 20.0，实际 {by_name[STUDENT_1]}"
    return json.dumps(data, ensure_ascii=False)


def test_progress_mark_unmark():
    data = expect(api("POST", "/api/progress/mark", json={
        "student_name": STUDENT_1, "scene_index": 1, "total_scenes": 10, "completed": False,
    }), 200, "取消第 2 节完成")
    assert data.get("completed") is False, f"completed 应为 False，实际 {data}"
    data = expect(api("GET", "/api/stats/progress"), 200, "取消后进度统计")
    by_name = {s["student_name"]: s for s in data.get("students", [])}
    assert by_name[STUDENT_1]["completed_count"] == 1, f"取消后应剩 1 节，实际 {by_name[STUDENT_1]}"
    return "completed_count=1"


def test_progress_mark_not_in_roster():
    expect(api("POST", "/api/progress/mark", json={
        "student_name": "不在名单", "scene_index": 0, "total_scenes": 10, "completed": True,
    }), 403, "名单外学生上报进度")
    return "返回 403"


def test_admin_deactivate():
    data = expect(api("POST", "/api/admin/students/deactivate", json={
        "admin_key": ADMIN_KEY, "student_name": STUDENT_2,
    }), 200, "移出名册")
    assert data.get("deactivated") == STUDENT_2, f"deactivated 应为 {STUDENT_2}，实际 {data}"
    data = expect(api("GET", "/api/admin/students", params={"admin_key": ADMIN_KEY}), 200, "移出后名单")
    s2 = next(s for s in data["students"] if s["name"] == STUDENT_2)
    assert s2["is_active"] is False, f"应停用，实际 {s2}"
    expect(api("POST", "/api/auth/login", json={"student_name": STUDENT_2, "password": DEFAULT_PWD}),
           404, "停用后登录")
    return "已停用且无法登录"


def test_admin_reactivate():
    data = expect(api("POST", "/api/admin/students/reactivate", json={
        "admin_key": ADMIN_KEY, "student_name": STUDENT_2,
    }), 200, "重新加入")
    assert data.get("reactivated") == STUDENT_2, f"reactivated 应为 {STUDENT_2}，实际 {data}"
    expect(api("POST", "/api/auth/login", json={"student_name": STUDENT_2, "password": DEFAULT_PWD}),
           200, "重新加入后登录")
    return "已恢复登录"


def test_admin_delete_student():
    before = expect(api("GET", "/api/answers/detail", params={"student_name": STUDENT_3}), 200, "删除前明细")
    assert len(before) == 2, "删除前应有 2 条记录"
    data = expect(api("POST", "/api/admin/students/delete", json={
        "admin_key": ADMIN_KEY, "student_name": STUDENT_3,
    }), 200, "删除学生")
    assert data.get("deleted") == STUDENT_3, f"deleted 应为 {STUDENT_3}，实际 {data}"
    assert data.get("removed_answers") == 2, f"应删除 2 条答题记录，实际 {data}"
    removed = data.get("removed_answers")
    data = expect(api("GET", "/api/admin/students", params={"admin_key": ADMIN_KEY}), 200, "删除后名单")
    names = [s["name"] for s in data["students"]]
    assert STUDENT_3 not in names, f"名单中不应再有 {STUDENT_3}"
    assert expect(api("GET", "/api/answers/detail", params={"student_name": STUDENT_3}), 200, "删除后明细") == []
    return f"removed_answers={removed}"


def test_admin_clear_all():
    data = expect(api("POST", "/api/admin/answers/clear", json={"admin_key": ADMIN_KEY}), 200, "一键清除")
    assert data.get("cleared_answers") == 5, f"应清除 5 条答题记录，实际 {data}"
    data = expect(api("GET", "/api/stats/overview"), 200, "清除后总览")
    assert data["total_answers"] == 0, f"清除后总答题数应为 0，实际 {data}"
    data = expect(api("GET", "/api/stats/progress"), 200, "清除后进度")
    assert all(s["completed_count"] == 0 for s in data["students"]), f"清除后进度应全部归零，实际 {data}"
    return "cleared_answers=3, progress reset"


ALL_TESTS = [
    ("GET / 学生端首页", test_root_page),
    ("POST /api/admin/students 上传名单", test_upload_roster),
    ("POST /api/admin/students 错误口令", test_upload_roster_wrong_key),
    ("GET /api/admin/students 查看名单", test_list_students),
    ("POST /api/auth/login 正常登录", test_login_ok),
    ("POST /api/auth/login 错误密码", test_login_wrong_password),
    ("POST /api/auth/login 名单外学生", test_login_not_in_roster),
    ("POST /api/auth/change-password 修改密码", test_change_password),
    ("POST /api/answers/submit 单条提交", test_submit_single),
    ("POST /api/answers/submit 带小节提交", test_submit_with_scene),
    ("POST /api/answers/submit 名单外提交", test_submit_not_in_roster),
    ("POST /api/answers/batch 批量提交", test_batch_submit),
    ("POST /api/answers/batch 空批量", test_batch_empty),
    ("GET /api/stats/overview 整体统计", test_stats_overview),
    ("GET /api/stats/questions 逐题统计", test_stats_questions),
    ("GET /api/stats/question-groups 分小节题目统计", test_stats_question_groups),
    ("GET /api/stats/students 逐学生统计", test_stats_students),
    ("GET /api/answers/detail 学生详情", test_answer_detail),
    ("GET /api/answers/detail 未知学生", test_answer_detail_unknown),
    ("POST /api/progress/mark 标记完成", test_progress_mark),
    ("POST /api/progress/sync 全量同步", test_progress_sync),
    ("GET /api/stats/progress 进度统计", test_progress_stats),
    ("POST /api/progress/mark 取消完成", test_progress_mark_unmark),
    ("POST /api/progress/mark 名单外学生", test_progress_mark_not_in_roster),
    ("POST /api/admin/students/deactivate 移出名册", test_admin_deactivate),
    ("POST /api/admin/students/reactivate 重新加入", test_admin_reactivate),
    ("POST /api/admin/students/delete 删除学生", test_admin_delete_student),
    ("POST /api/admin/answers/clear 一键清除", test_admin_clear_all),
]


# ---------------------------------------------------------------------------
# 后端进程管理
# ---------------------------------------------------------------------------

def server_ready() -> bool:
    try:
        resp = requests.get(BASE_URL + "/api/stats/overview", timeout=2)
        return resp.status_code < 500
    except requests.RequestException:
        return False


def start_temp_server() -> tuple:
    """在临时目录启动 uvicorn：SQLite 文件会落在临时目录，不污染正式数据库。"""
    tmp = tempfile.TemporaryDirectory(prefix="answer_test_")
    log_path = Path(tmp.name) / "server.log"
    log_file = open(log_path, "wb")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--app-dir", str(PROJECT_DIR),
            "--host", "127.0.0.1", "--port", "8000",
        ],
        cwd=tmp.name,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            log_file.close()
            raise RuntimeError(
                f"临时后端启动失败，退出码 {proc.returncode}，日志：\n"
                f"{log_path.read_text(encoding='utf-8', errors='replace')[-2000:]}"
            )
        if server_ready():
            return proc, tmp, log_file
        time.sleep(0.5)

    proc.terminate()
    log_file.close()
    raise RuntimeError("等待后端就绪超时（30 秒），请检查 uvicorn 是否可正常启动。")


def main() -> int:
    parser = argparse.ArgumentParser(description="互动课堂答题系统 API 自动化测试")
    parser.add_argument("--use-existing", action="store_true",
                        help="使用已运行在 8000 端口的后端（会写入其真实数据库）")
    args = parser.parse_args()

    proc = tmp = log_file = None
    try:
        if args.use_existing:
            if not server_ready():
                print("[错误] 8000 端口没有可用的后端服务，请先启动 `python main.py`。")
                return 2
            print("[信息] 使用已运行的后端，测试数据会写入其真实数据库。")
        else:
            if server_ready():
                print("[错误] 8000 端口已有后端在运行。为避免污染正式数据库，请先停止它，")
                print("       或使用 `python test_api.py --use-existing` 明确对现有后端测试。")
                return 2
            proc, tmp, log_file = start_temp_server()
            print("[信息] 已启动临时后端（独立临时数据库，测试结束后自动清理）。")

        print(f"开始测试，Base URL：{BASE_URL}\n")
        for name, fn in ALL_TESTS:
            run_test(name, fn)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            if log_file:
                log_file.close()
            if tmp:
                # Windows 上进程退出后文件句柄可能延迟释放，重试清理临时目录
                for _attempt in range(10):
                    try:
                        tmp.cleanup()
                        break
                    except PermissionError:
                        time.sleep(0.5)
            print("\n[信息] 临时后端已停止，临时数据库已清理。")

    print(f"\n===== 汇总：通过 {len(passed)} / {len(passed) + len(failed)} =====")
    if failed:
        print("失败用例：")
        for name in failed:
            print("  - " + name)
        return 1
    print("全部用例通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
