#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - add_memory 工具方法
==============================================
添加一条新记忆并自动维护索引。
每条记忆生成一个独立文件，按类别存入子目录。
可独立调用：python scripts/add_memory.py --category habit --content "..." [--priority high] [--tags tag1,tag2]
"""

import sys
import json
import re
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        get_entry_file_path, read_memory_file, write_memory_file,
        read_memory_index, write_memory_index,
        now_iso, now_date_str, generate_entry_id, MEMORY_DIR,
        ARCHIVE_THRESHOLD, ARCHIVE_AGE_DAYS, ARCHIVE_AGE_DAYS_FALLBACK,
        CATEGORY_DIR_MAP, days_since
    )
except ImportError:
    from _base import (
        get_entry_file_path, read_memory_file, write_memory_file,
        read_memory_index, write_memory_index,
        now_iso, now_date_str, generate_entry_id, MEMORY_DIR,
        ARCHIVE_THRESHOLD, ARCHIVE_AGE_DAYS, ARCHIVE_AGE_DAYS_FALLBACK,
        CATEGORY_DIR_MAP, days_since
    )


def _generate_summary(content: str, max_len: int = 80) -> str:
    """从内容生成简短摘要"""
    text = re.sub(r'[#*_`\[\](){}]', '', content)
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _update_index_for_entry(file_rel_path: str, category: str, summary: str,
                             priority: str, tags: list, entry_id: str,
                             project_name: str = None,
                             emphasis: bool = False, mention_count: int = 0,
                             memory_dir=None):
    """更新总目录中该条目的记录"""
    index_fm = read_memory_index(memory_dir=memory_dir)
    entries_list = index_fm.get("entries", [])

    entry_data = {
        "path": file_rel_path,
        "category": category,
        "summary": summary,
        "priority": priority,
        "tags": tags,
        "entry_id": entry_id,
        "last_modified": now_iso(),
        "emphasis": emphasis,
    }

    # skill 类别记录提及次数
    if category == "skill" and mention_count > 0:
        entry_data["mention_count"] = mention_count

    if category == "project" and project_name:
        entry_data["title"] = project_name

    # 查找是否已存在同 entry_id 的记录
    existing_idx = None
    for i, e in enumerate(entries_list):
        if isinstance(e, dict) and e.get("entry_id") == entry_id:
            existing_idx = i
            break

    if existing_idx is not None:
        entries_list[existing_idx] = entry_data
    else:
        entries_list.insert(0, entry_data)

    index_fm["entries"] = entries_list
    index_fm["last_modified"] = now_iso()
    write_memory_index(index_fm, memory_dir=memory_dir)


def _check_archiving(category: str, memory_dir: Path = None) -> dict:
    """
    检查并执行归档（当类别目录下文件数超过阈值时）
    将低优先级且过期的条目文件移入 archive 子目录，并同步更新总目录索引
    """
    mem_dir = memory_dir or MEMORY_DIR
    cat_dir = mem_dir / CATEGORY_DIR_MAP.get(category, category)
    if not cat_dir.exists():
        return {"archived": False, "count": 0}

    # 统计该类别下的文件数
    md_files = list(cat_dir.glob("*.md"))
    if len(md_files) <= ARCHIVE_THRESHOLD:
        return {"archived": False, "count": 0}

    # 筛选低优且旧的文件
    archive_dir = cat_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    archived_count = 0
    archived_paths = []  # 记录被归档的文件相对路径

    def _archive_round(files, age_threshold):
        """执行一轮归档"""
        count = 0
        moved = []
        for md_file in files:
            if not md_file.exists():
                continue
            fm, _ = read_memory_file(md_file)
            if not fm:
                continue
            priority = fm.get("priority", "low")
            date_str = fm.get("date", "")
            if priority == "low" and days_since(date_str) > age_threshold:
                dest = archive_dir / md_file.name
                md_file.rename(dest)
                count += 1
                try:
                    moved.append(str(md_file.relative_to(mem_dir)))
                except ValueError:
                    pass
        return count, moved

    # 第一轮：90天阈值
    archived_count, archived_paths = _archive_round(md_files, ARCHIVE_AGE_DAYS)

    # 第二轮：若归档后仍超阈值，用60天阈值
    remaining = list(cat_dir.glob("*.md"))
    if len(remaining) > ARCHIVE_THRESHOLD:
        round2_count, round2_paths = _archive_round(remaining, ARCHIVE_AGE_DAYS_FALLBACK)
        archived_count += round2_count
        archived_paths.extend(round2_paths)

    # 同步更新总目录索引中对应条目的路径
    if archived_paths:
        index_fm = read_memory_index(memory_dir=mem_dir)
        cat_dir_name = CATEGORY_DIR_MAP.get(category, category)
        for old_rel_path in archived_paths:
            for entry in index_fm.get("entries", []):
                if isinstance(entry, dict) and entry.get("path") == old_rel_path:
                    # 更新路径指向 archive 子目录
                    file_name = Path(old_rel_path).name
                    entry["path"] = f"{cat_dir_name}/archive/{file_name}"
        write_memory_index(index_fm, memory_dir=mem_dir)

    return {"archived": archived_count > 0, "count": archived_count}


def add_memory(
    category: str,
    content: str,
    priority: str = "medium",
    tags: list = None,
    expires: str = None,
    related: list = None,
    project_name: str = None,
    emphasis: bool = False,
    mention_count: int = 0,
    memory_dir: Path = None
) -> dict:
    """
    添加一条新记忆，生成独立文件并更新索引。

    参数:
        category: habit/skill/project
        content: 记忆正文(Markdown)
        priority: high/medium/low
        tags: 标签列表
        expires: 过期日期(ISO)或None
        related: 关联文件列表
        project_name: 项目名称(category=project时必填)
        emphasis: 是否被用户主动强调/标记重点（影响加权检索权重）
        mention_count: 被提及的次数（skill类别使用，>=3视为反复提及）
        memory_dir: 自定义记忆目录(默认使用配置值)

    返回:
        {"success": True, "entry_id": "...", "file_path": "..."}
    """
    tags = tags or []
    related = related or []

    # 1. 生成摘要和 entry_id
    summary = _generate_summary(content)

    # 先生成 entry_id（需要检查所有类别的已有文件，避免跨类别ID冲突）
    mem_dir = memory_dir or MEMORY_DIR
    existing_ids = []
    for cat_name in CATEGORY_DIR_MAP.values():
        cat_dir = mem_dir / cat_name
        if cat_dir.exists():
            for f in cat_dir.glob("*.md"):
                fm, _ = read_memory_file(f)
                if fm and fm.get("entry_id"):
                    existing_ids.append(fm["entry_id"])

    entry_id = generate_entry_id(existing_ids)
    now = now_iso()
    date_header = now_date_str()

    # 2. 生成文件路径
    file_path = get_entry_file_path(category, entry_id, summary, project_name, memory_dir=mem_dir)

    # 3. 对于项目类型，如果文件已存在则追加
    if category == "project" and file_path.exists():
        fm, body = read_memory_file(file_path)
        # 在正文顶部追加新内容
        new_block = (
            f"### {summary}\n\n"
            f"**ID**: `{entry_id}`  \n"
            f"**时间**: {date_header}  \n"
            f"**优先级**: {priority}  \n"
            f"**标签**: {', '.join(tags) if tags else '无'}  \n"
            f"**过期**: {expires or '永不过期'}  \n\n"
            f"{content}\n\n"
            "---\n\n"
        )
        body = new_block + body
        fm["last_modified"] = now
        if "decision_log" not in fm:
            fm["decision_log"] = []
        fm["decision_log"].insert(0, {
            "date": now,
            "decision": summary,
            "entry_id": entry_id
        })
        write_memory_file(file_path, fm, body)
    else:
        # 4. 创建新的独立记忆文件
        fm = {
            "entry_id": entry_id,
            "date": now,
            "category": category,
            "priority": priority,
            "tags": tags,
            "summary": summary,
            "expires": expires,
            "related_files": related,
            "last_modified": now,
            "emphasis": emphasis,
        }

        # skill 类别记录提及次数
        if category == "skill" and mention_count > 0:
            fm["mention_count"] = mention_count

        if category == "project" and project_name:
            fm["project_name"] = project_name
            fm["status"] = "active"

        body = content + "\n"

        write_memory_file(file_path, fm, body)

    # 5. 更新总目录
    file_rel_path = str(file_path.relative_to(mem_dir))
    _update_index_for_entry(file_rel_path, category, summary, priority, tags, entry_id, project_name, emphasis, mention_count, memory_dir=mem_dir)

    # 6. 归档检查
    cat_dir = mem_dir / CATEGORY_DIR_MAP.get(category, category)
    if cat_dir.exists():
        file_count = len(list(cat_dir.glob("*.md")))
        if file_count > ARCHIVE_THRESHOLD:
            archive_result = _check_archiving(category, memory_dir=mem_dir)
            if archive_result["archived"]:
                return {
                    "success": True,
                    "entry_id": entry_id,
                    "file_path": file_rel_path,
                    "archive_notice": f"已归档 {archive_result['count']} 条旧记忆"
                }

    return {
        "success": True,
        "entry_id": entry_id,
        "file_path": file_rel_path,
        "notice": "记忆已保存为独立文件"
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
    parser.add_argument("--emphasis", action="store_true", help="标记为用户主动强调/重点")
    parser.add_argument("--mention-count", type=int, default=0, help="提及次数(skill类别，>=3视为反复提及)")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()
    tags_list = [t.strip() for t in args.tags.split(",")] if args.tags else []

    result = add_memory(
        category=args.category,
        content=args.content,
        priority=args.priority,
        tags=tags_list,
        expires=args.expires,
        project_name=args.project_name,
        emphasis=args.emphasis,
        mention_count=args.mention_count
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
