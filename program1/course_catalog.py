# course_catalog.py
# 从学生端页面 student.html 中解析课程目录（小节 + 随堂测验题目），
# 供教师端“答题情况”统计按小节分组，并为旧答题记录回填小节信息。

from pathlib import Path
import re

STUDENT_PAGE = Path(__file__).resolve().parent / "student.html"

_cache: dict | None = None


def _skip_quoted(text: str, i: int, quote: str) -> int:
    """跳过双引号/单引号字符串，返回字符串结束后的下标。"""
    i += 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        i += 1
    return i


def _strip_comments(text: str) -> str:
    """去除 JS 注释（// 与 /* */），字符串内内容不受影响。"""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ('"', "'"):
            j = _skip_quoted(text, i, ch)
            out.append(text[i:j])
            i = j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = j if j != -1 else n
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _find_matching(text: str, open_idx: int) -> int:
    """从开括号 open_idx 起，匹配到对应闭括号（忽略字符串内容）。"""
    open_ch = text[open_idx]
    close_ch = {"{": "}", "[": "]", "(": ")"}[open_ch]
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ('"', "'"):
            i = _skip_quoted(text, i, ch)
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"未找到与 {open_ch} 匹配的闭合括号")


def _object_texts(text: str, start: int, end: int) -> list[str]:
    """在 [start, end) 范围内提取顶层 {...} 对象原文列表。"""
    objs: list[str] = []
    i = start
    while i < end:
        j = text.find("{", i, end)
        if j < 0:
            break
        k = _find_matching(text, j)
        objs.append(text[j : k + 1])
        i = k + 1
    return objs


def _field(obj: str, name: str) -> str | None:
    """提取对象中的字符串字段，如 q: "..."。"""
    m = re.search(name + r'\s*:\s*"((?:[^"\\]|\\.)*)"', obj)
    return m.group(1) if m else None


def _parse_options(obj: str) -> list[str]:
    m = re.search(r"options\s*:\s*\[", obj)
    if not m:
        return []
    open_idx = obj.find("[", m.start())
    close_idx = _find_matching(obj, open_idx)
    return re.findall(r'"((?:[^"\\]|\\.)*)"', obj[open_idx : close_idx + 1])


def _parse_answer(obj: str):
    """提取 answer 字段：单个数字 -> int，数组 -> list[int]，否则 None。"""
    m = re.search(r"answer\s*:\s*(\[[^\[\]]*\]|\d+)", obj)
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith("["):
        return [int(x) for x in re.findall(r"\d+", raw)]
    return int(raw)


def _correct_answer_text(obj: str, options: list[str], answer) -> str:
    """与学生端一致：选择题取选项文本，问答题取参考答案/解析。"""
    if isinstance(answer, int) and 0 <= answer < len(options):
        return options[answer]
    if isinstance(answer, list):
        picked = [options[i] for i in answer if 0 <= i < len(options)]
        if picked:
            return "、".join(picked)
    return _field(obj, "reference") or _field(obj, "explanation") or ""


def load_course_catalog() -> dict:
    """解析学生端页面的课程目录，返回 {scenes: [{scene_index, scene_title, questions: [...]}]}。

    仅收录 type 为 quiz 的小节（随堂测验），题目按页内顺序编号（0 起）。
    解析结果按文件内容缓存，进程内只解析一次。
    """
    global _cache
    if _cache is not None:
        return _cache

    raw = STUDENT_PAGE.read_text(encoding="utf-8")
    start = raw.find("const COURSE = {")
    if start < 0:
        raise RuntimeError("student.html 中未找到 COURSE 定义，无法解析课程目录")
    scenes_marker = raw.find("scenes: [", start)
    if scenes_marker < 0:
        raise RuntimeError("student.html COURSE 中未找到 scenes 数组")
    open_idx = raw.find("[", scenes_marker)
    close_idx = _find_matching(raw, open_idx)
    region = _strip_comments(raw[open_idx : close_idx + 1])

    scenes: list[dict] = []
    for scene_index, obj in enumerate(_object_texts(region, 0, len(region))):
        if _field(obj, "type") != "quiz":
            continue
        title = _field(obj, "title")
        if not title:
            continue
        q_marker = obj.find("questions: [")
        if q_marker < 0:
            continue
        q_open = obj.find("[", q_marker)
        q_close = _find_matching(obj, q_open)
        questions: list[dict] = []
        for q_obj in _object_texts(obj, q_open, q_close):
            q_text = _field(q_obj, "q")
            if not q_text:
                continue
            options = _parse_options(q_obj)
            answer = _parse_answer(q_obj)
            questions.append(
                {
                    "question_index": len(questions),
                    "question_title": q_text,
                    "correct_answer": _correct_answer_text(q_obj, options, answer),
                }
            )
        if questions:
            scenes.append(
                {
                    "scene_index": scene_index,
                    "scene_title": title,
                    "questions": questions,
                }
            )
    _cache = {"scenes": scenes}
    return _cache


def title_to_scene_map() -> dict[str, tuple[int, str]]:
    """题目内容 -> (scene_index, scene_title)，用于旧记录回填。"""
    result: dict[str, tuple[int, str]] = {}
    for scene in load_course_catalog()["scenes"]:
        for q in scene["questions"]:
            result[q["question_title"]] = (scene["scene_index"], scene["scene_title"])
    return result


def backfill_scene_info(db) -> int:
    """为 scene_index 为空的历史答题记录回填小节信息（按题目内容匹配），返回更新条数。"""
    from models import AnswerRecord

    mapping = title_to_scene_map()
    if not mapping:
        return 0
    records = db.query(AnswerRecord).filter(AnswerRecord.scene_index.is_(None)).all()
    updated = 0
    for r in records:
        hit = mapping.get(r.question_title)
        if hit:
            r.scene_index, r.scene_title = hit
            updated += 1
    if updated:
        db.commit()
    return updated
