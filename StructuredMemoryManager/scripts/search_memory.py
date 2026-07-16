#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - search_memory 工具方法
=================================================
执行二级检索机制：总目录粗筛 → 独立文件精读。
可独立调用：python scripts/search_memory.py "查询关键词" [--category habit] [--high-priority]
"""

import sys
import json
import re
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_index, read_memory_file, is_expired,
        MEMORY_DIR, CATEGORY_DIR_MAP
    )
except ImportError:
    from _base import (
        read_memory_index, read_memory_file, is_expired,
        MEMORY_DIR, CATEGORY_DIR_MAP
    )


def read_memory(
    file_path: str,
    memory_dir: Path = None
) -> dict:
    """
    读取单条记忆的完整内容

    参数:
        file_path: 目标文件路径（相对于memory目录）
        memory_dir: 自定义记忆目录

    返回:
        {"entry_id", "category", "priority", "tags", "summary", "content", ...}
    """
    mem_dir = memory_dir or MEMORY_DIR
    abs_path = mem_dir / file_path

    if not abs_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    fm, body = read_memory_file(abs_path)

    return {
        "success": True,
        "file_path": file_path,
        "entry_id": fm.get("entry_id"),
        "category": fm.get("category"),
        "priority": fm.get("priority"),
        "tags": fm.get("tags", []),
        "summary": fm.get("summary", ""),
        "expires": fm.get("expires"),
        "date": fm.get("date"),
        "last_modified": fm.get("last_modified"),
        "content": body.strip(),
    }


def search_memory(
    query: str,
    category_filter: str = None,
    tag_filter: list = None,
    high_priority_only: bool = False,
    memory_dir: Path = None
) -> list:
    """
    执行二级检索：总目录粗筛 → 独立文件精读

    参数:
        query: 检索查询词或自然语言问题
        category_filter: 类别过滤 habit/skill/project，None=不过滤
        tag_filter: 标签过滤列表
        high_priority_only: 是否仅返回高优先级条目
        memory_dir: 自定义记忆目录

    返回:
        [{"file_path", "entry_id", "summary", "content_snippet", "score", "priority", "tags"}]
    """
    tag_filter = tag_filter or []
    results = []
    mem_dir = memory_dir or MEMORY_DIR

    # === 第一级：总目录粗筛 ===
    index_fm = read_memory_index()
    candidate_entries = []

    for entry_info in index_fm.get("entries", []):
        if not isinstance(entry_info, dict):
            continue

        # 类别过滤
        if category_filter and entry_info.get("category") != category_filter:
            continue

        entry_score = 0
        query_lower = query.lower()
        summary = entry_info.get("summary", "")
        entry_tags = entry_info.get("tags", [])
        entry_priority = entry_info.get("priority", "low")

        # 摘要匹配
        if query and any(qw in summary.lower() for qw in query_lower.split()):
            entry_score += 3

        # 标签匹配
        if query:
            for tag in entry_tags:
                if any(qw in tag.lower() for qw in query_lower.split()):
                    entry_score += 2

        # tag_filter 过滤
        if tag_filter and not any(tf in entry_tags for tf in tag_filter):
            continue

        # 高优过滤
        if high_priority_only and entry_priority != "high":
            continue

        # 过期条目降权
        expires = entry_info.get("expires")
        if expires and is_expired(expires):
            entry_score -= 1

        if entry_score > 0 or not query:
            candidate_entries.append((entry_info, entry_score))

    # 按分数排序
    candidate_entries.sort(key=lambda x: x[1], reverse=True)
    candidate_entries = candidate_entries[:10]

    # === 第二级：读取独立文件获取完整内容 ===
    for entry_info, score in candidate_entries:
        file_rel_path = entry_info.get("path", "")
        file_abs_path = mem_dir / file_rel_path

        if not file_abs_path.exists():
            continue

        fm, body = read_memory_file(file_abs_path)

        # 提取内容片段
        content_snippet = body.strip()
        if len(content_snippet) > 300:
            content_snippet = content_snippet[:300] + "..."

        results.append({
            "file_path": file_rel_path,
            "entry_id": entry_info.get("entry_id"),
            "summary": entry_info.get("summary", ""),
            "content_snippet": content_snippet,
            "score": score,
            "priority": entry_info.get("priority", "medium"),
            "tags": entry_info.get("tags", []),
            "date": entry_info.get("last_modified") or fm.get("date"),
        })

    # 按分数排序返回
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:10]


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 检索/读取记忆")
    subparsers = parser.add_subparsers(dest="command")

    # search 子命令
    search_parser = subparsers.add_parser("search", help="检索记忆")
    search_parser.add_argument("query", help="检索查询词")
    search_parser.add_argument("--category", "-c", choices=["habit", "skill", "project"],
                        help="类别过滤")
    search_parser.add_argument("--tags", "-t", default="", help="标签过滤，逗号分隔")
    search_parser.add_argument("--high-priority", action="store_true", help="仅高优先级")

    # read 子命令
    read_parser = subparsers.add_parser("read", help="读取单条记忆完整内容")
    read_parser.add_argument("file_path", help="目标文件路径（相对memory目录）")

    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    if args.command == "read":
        result = read_memory(file_path=args.file_path)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    elif args.command == "search":
        tags_list = [t.strip() for t in args.tags.split(",")] if args.tags else []
        results = search_memory(
            query=args.query,
            category_filter=args.category,
            tag_filter=tags_list,
            high_priority_only=args.high_priority
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            if not results:
                print(f"未找到与「{args.query}」相关的记忆。")
            else:
                print(f"找到 {len(results)} 条相关记忆:\n")
                for i, r in enumerate(results, 1):
                    print(f"[{i}] ({r['priority']}) {r['summary']}")
                    print(f"    文件: {r['file_path']} | ID: {r['entry_id']} | 分数: {r['score']}\n")
    else:
        parser.print_help()
