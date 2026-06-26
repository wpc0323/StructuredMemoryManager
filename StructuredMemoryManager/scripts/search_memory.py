#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - search_memory 工具方法
=================================================
执行三级检索机制：总目录粗筛 → 内部索引精读 → 正文精确提取。
可独立调用：python scripts/search_memory.py "查询关键词" [--category habit] [--high-priority]
"""

import sys
import json
import re
import argparse
from pathlib import Path

# 导入共享基础模块
from ._base import (
    read_memory_index, read_memory_file, is_expired,
    MEMORY_DIR
)


def _extract_body_entry(body: str, entry_id: str, summary: str, max_chars: int = 300) -> str:
    """
    从正文中提取指定条目的内容片段
    通过ID锚点定位，若找不到则返回摘要
    """
    # 尝试通过ID查找
    pattern = rf'###.*?`{re.escape(entry_id)}`.*?\n\n(.*?)(?:---|\n### |\Z)'
    match = re.search(pattern, body, re.DOTALL)
    if match:
        snippet = match.group(1).strip()
        snippet = re.sub(r'\n+', ' ', snippet)
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars] + "..."
        return snippet

    # 回退：通过摘要关键词在正文中搜索
    keywords = summary.split()[:5]
    for kw in keywords[:3]:
        kw_pattern = rf'.*{re.escape(kw)}.*'
        kw_match = re.search(kw_pattern, body, re.DOTALL | re.IGNORECASE)
        if kw_match:
            snippet = kw_match.group(0).strip()
            snippet = re.sub(r'\n+', ' ', snippet)
            if len(snippet) > max_chars:
                snippet = snippet[:max_chars] + "..."
            return snippet

    return summary


def search_memory(
    query: str,
    category_filter: str = None,
    tag_filter: list = None,
    high_priority_only: bool = False,
    memory_dir: Path = None
) -> list:
    """
    执行三级检索：总目录粗筛 → 内部索引精读 → 正文提取

    参数:
        query: 检索查询词或自然语言问题
        category_filter: 类别过滤 habit/skill/project，None=不过滤
        tag_filter: 标签过滤列表
        high_priority_only: 是否仅返回高优先级条目
        memory_dir: 自定义记忆目录

    返回:
        [{"file_path", "entry_id", "anchor", "content_snippet", "score", "priority", "tags"}]
    """
    tag_filter = tag_filter or []
    results = []
    mem_dir = memory_dir or MEMORY_DIR

    # === 第一级：总目录粗筛 ===
    index_fm = read_memory_index()
    candidate_files = []

    for file_info in index_fm.get("files", []):
        # 类别过滤
        if category_filter and file_info.get("category") != category_filter:
            continue

        # 标签匹配（计算相关度分数）
        score = 0
        file_tags = file_info.get("tags", [])
        high_tags = file_info.get("high_priority_tags", [])

        # 查询关键词匹配标签
        query_lower = query.lower()
        for tag in file_tags:
            if any(qw in tag.lower() for qw in query_lower.split()):
                score += 2
        for tag in high_tags:
            if any(qw in tag.lower() for qw in query_lower.split()):
                score += 5  # 高优标签加权

        # tag_filter 过滤
        if tag_filter:
            if not any(tf in file_tags for tf in tag_filter):
                continue

        # 高优过滤
        if high_priority_only and not high_tags:
            continue

        if score > 0 or not query:  # 有匹配或无条件查询
            candidate_files.append((file_info, score))

    # 按分数排序
    candidate_files.sort(key=lambda x: x[1], reverse=True)
    # 取前5个候选文件
    candidate_files = candidate_files[:5]

    # === 第二级：内部索引精读 ===
    for file_info, _ in candidate_files:
        file_rel_path = file_info["path"]
        file_abs_path = mem_dir / file_rel_path

        if not file_abs_path.exists():
            continue

        fm, body = read_memory_file(file_abs_path)
        entries = fm.get("internal_index", fm.get("decision_log", []))

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            entry_score = 0
            summary = entry.get("summary", "")
            entry_tags = entry.get("tags", [])
            entry_priority = entry.get("priority", "low")

            # 摘要匹配
            if query_lower in summary.lower():
                entry_score += 3

            # 标签匹配
            for tag in entry_tags:
                if query_lower in tag.lower():
                    entry_score += 2

            # tag_filter
            if tag_filter and not any(tf in entry_tags for tf in tag_filter):
                continue

            # 高优过滤
            if high_priority_only and entry_priority != "high":
                continue

            # 过期条目降权
            expires = entry.get("expires")
            if expires and is_expired(expires):
                entry_score -= 1

            if entry_score > 0 or not query:
                # === 第三级：正文提取 ===
                content_snippet = _extract_body_entry(
                    body, entry.get("entry_id", ""), summary
                )

                results.append({
                    "file_path": file_rel_path,
                    "entry_id": entry.get("entry_id"),
                    "anchor": f"#{entry.get('entry_id', '')}",
                    "content_snippet": content_snippet,
                    "score": entry_score,
                    "priority": entry_priority,
                    "tags": entry_tags,
                    "date": entry.get("date")
                })

    # 按分数排序返回
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:10]  # 最多返回10条


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 检索记忆")
    parser.add_argument("query", help="检索查询词")
    parser.add_argument("--category", "-c", choices=["habit", "skill", "project"],
                        help="类别过滤")
    parser.add_argument("--tags", "-t", default="", help="标签过滤，逗号分隔")
    parser.add_argument("--high-priority", action="store_true", help="仅高优先级")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()
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
                print(f"[{i}] ({r['priority']}) {r['content_snippet'][:100]}...")
                print(f"    文件: {r['file_path']} | ID: {r['entry_id']} | 分数: {r['score']}\n")
