#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - add_memory 工具方法
==============================================
添加一条新记忆并自动维护所有索引。
可独立调用：python scripts/add_memory.py --category habit --content "..." [--priority high] [--tags tag1,tag2]
"""

import sys
import json
from pathlib import Path

# 导入共享基础模块
from ._base import (
    get_file_path, read_memory_file, write_memory_file,
    init_from_template, read_memory_index, write_memory_index,
    now_iso, now_date_str, generate_entry_id, MEMORY_DIR,
    ARCHIVE_THRESHOLD
)


def _generate_summary(content: str, max_len: int = 80) -> str:
    """从内容生成简短摘要"""
    # 移除Markdown标记
    text = re.sub(r'[#*_`\[\](){}]', '', content)
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _update_index_for_file(file_rel_path: str, fm: dict, category: str, project_name: str = None):
    """更新总目录中对应文件的记录"""
    index_fm = read_memory_index()
    files_list = index_fm.get("files", [])

    # 查找是否已存在
    existing = None
    for f in files_list:
        if f.get("path") == file_rel_path:
            existing = f
            break

    entry_data = {
        "path": file_rel_path,
        "category": category,
        "tags": fm.get("priority_tags", []),
        "last_modified": fm.get("last_modified", now_iso()),
        "high_priority_tags": fm.get("priority_tags", []),
    }

    if category == "project" and project_name:
        entry_data["title"] = project_name

    related_files = fm.get("related_files", [])
    if related_files:
        entry_data["related"] = [
            f"{rf}#{tag}" for rf in related_files for tag in (fm.get("priority_tags", [])[:1] or [""])
        ] or None

    if existing:
        # 更新现有记录
        existing.update(entry_data)
    else:
        # 新增记录
        files_list.append(entry_data)

    index_fm["files"] = files_list
    index_fm["last_modified"] = now_iso()
    write_memory_index(index_fm)


def _check_archiving(category: str) -> dict:
    """检查并执行归档（当条目数超过阈值时）"""
    from ._base import get_file_path, read_memory_file, write_memory_file, days_since, ARCHIVE_AGE_DAYS, MEMORY_DIR

    file_name = {
        "habit": "habits_preferences.md",
        "skill": "skills_methods.md"
    }.get(category)

    if not file_name:
        return {"archived": False, "count": 0}

    target_path = MEMORY_DIR / file_name
    archive_name = file_name.replace(".md", "_archive.md")
    archive_path = MEMORY_DIR / archive_name

    if not target_path.exists():
        return {"archived": False, "count": 0}

    fm, body = read_memory_file(target_path)
    entries = list(fm.get("internal_index", []))

    if len(entries) <= ARCHIVE_THRESHOLD:
        return {"archived": False, "count": 0}

    # 筛选低优且旧的条目
    now_dt = __import__("datetime").datetime.now(__import__("datetime").timezone(__import__("datetime").timedelta(hours=8)))
    to_archive = []
    to_keep = []

    for entry in entries:
        if not isinstance(entry, dict):
            to_keep.append(entry)
            continue

        priority = entry.get("priority", "low")
        date_str = entry.get("date", "")

        if priority == "low" and days_since(date_str) > ARCHIVE_AGE_DAYS:
            to_archive.append(entry)
        else:
            to_keep.append(entry)

    if not to_archive:
        return {"archived": False, "count": 0}

    # 执行归档
    if archive_path.exists():
        arch_fm, arch_body = read_memory_file(archive_path)
        arch_entries = list(arch_fm.get("internal_index", []))
    else:
        arch_fm = {"category": category, "archive": True, "internal_index": []}
        arch_body = f"# {file_name.replace('.md', '')} 归档\n\n本文件包含已归档的旧条目。\n\n---\n\n"

    # 将归档条目加入归档文件（按日期排序）
    arch_entries.extend(to_archive)
    arch_entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    arch_fm["internal_index"] = arch_entries
    arch_fm["last_modified"] = now_iso()

    # 更新原文件
    fm["internal_index"] = to_keep
    fm["archive"] = archive_name
    fm["last_modified"] = now_iso()
    write_memory_file(target_path, fm, body)

    write_memory_file(archive_path, arch_fm, arch_body)

    return {"archived": True, "count": len(to_archive)}


def add_memory(
    category: str,
    content: str,
    priority: str = "medium",
    tags: list = None,
    expires: str = None,
    related: list = None,
    project_name: str = None,
    memory_dir: Path = None
) -> dict:
    """
    添加一条新记忆并自动维护所有索引。

    参数:
        category: habit/skill/project
        content: 记忆正文(Markdown)
        priority: high/medium/low
        tags: 标签列表
        expires: 过期日期(ISO)或None
        related: 关联文件列表
        project_name: 项目名称(category=project时必填)
        memory_dir: 自定义记忆目录(默认使用配置值)

    返回:
        {"success": True, "entry_id": "...", "file_path": "..."}
    """
    import re
    tags = tags or []
    related = related or []

    # 1. 确定目标文件
    file_path = get_file_path(category, project_name)

    # 2. 文件不存在则从模板初始化
    if not file_path.exists():
        init_from_template(category, project_name)

    # 3. 读取现有内容
    fm, body = read_memory_file(file_path)
    existing_ids = [
        entry.get("entry_id", "")
        for entry in fm.get("internal_index", fm.get("decision_log", []))
        if isinstance(entry, dict)
    ]

    # 4. 生成条目信息
    entry_id = generate_entry_id(existing_ids)
    now = now_iso()
    date_header = now_date_str()

    # 5. 构建新条目
    new_entry = {
        "date": now,
        "priority": priority,
        "summary": _generate_summary(content),
        "tags": tags,
        "expires": expires,
        "entry_id": entry_id
    }

    # 6. 插入internal_index顶部（时间倒序）
    if "internal_index" not in fm:
        fm["internal_index"] = []
    fm["internal_index"].insert(0, new_entry)

    # 7. 构建正文条目
    content_block = (
        f"### {date_header}\n\n"
        f"**ID**: `{entry_id}`  \n"
        f"**优先级**: {priority}  \n"
        f"**标签**: {', '.join(tags) if tags else '无'}  \n"
        f"**过期**: {expires or '永不过期'}  \n\n"
        f"{content}\n\n"
        "---\n\n"
    )

    # 8. 在正文顶部插入
    body = content_block + body

    # 9. 更新元数据
    fm["last_modified"] = now

    # 合并priority_tags
    existing_ptags = set(fm.get("priority_tags", []) or [])
    if priority == "high":
        existing_ptags.update(tags)
    fm["priority_tags"] = list(existing_ptags)

    # 更新related_files
    if related:
        existing_related = set(fm.get("related_files") or [])
        existing_related.update(related)
        fm["related_files"] = list(existing_related)

    # 10. 写入文件
    write_memory_file(file_path, fm, body)

    # 11. 更新总目录
    _update_index_for_file(str(file_path.relative_to(memory_dir or MEMORY_DIR)), fm, category, project_name)

    # 12. 归档检查
    index_count = len(fm.get("internal_index", []))
    if index_count > ARCHIVE_THRESHOLD:
        archive_result = _check_archiving(category)
        if archive_result["archived"]:
            return {
                "success": True,
                "entry_id": entry_id,
                "file_path": str(file_path.relative_to(memory_dir or MEMORY_DIR)),
                "archive_notice": f"已归档 {archive_result['count']} 条旧记忆"
            }

    return {
        "success": True,
        "entry_id": entry_id,
        "file_path": str(file_path.relative_to(memory_dir or MEMORY_DIR)),
        "notice": f"文件当前共 {index_count} 条记忆"
    }


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 添加记忆")
    parser.add_argument("--category", "-c", required=True, choices=["habit", "skill", "project"],
                        help="记忆类别")
    parser.add_argument("--content", required=True, help="记忆内容")
    parser.add_argument("--priority", "-p", default="medium", choices=["high", "medium", "low"],
                        help="优先级")
    parser.add_argument("--tags", "-t", default="", help="标签，逗号分隔")
    parser.add_argument("--expires", "-e", default=None, help="过期日期 ISO 8601")
    parser.add_argument("--project-name", default=None, help="项目名称(project类别必填)")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()
    tags_list = [t.strip() for t in args.tags.split(",")] if args.tags else []

    result = add_memory(
        category=args.category,
        content=args.content,
        priority=args.priority,
        tags=tags_list,
        expires=args.expires,
        project_name=args.project_name
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
