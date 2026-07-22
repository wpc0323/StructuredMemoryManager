#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - search_memory 工具方法
=================================================
执行加权二级检索机制：总目录粗筛 → 独立文件精读。
检索排序遵循记忆读取加权检索规范：
  - 分类1(project): 时间时效性 > 用户强调/标记重点 > 常规记录
  - 分类2(habit): 用户强调/明确要求 > 时间时效性 > 次要偏好
  - 分类3(skill): 用户强调/反复提及 > 其余全部
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
        MEMORY_DIR, CATEGORY_DIR_MAP,
        compute_weight, resolve_conflict,
    )
except ImportError:
    from _base import (
        read_memory_index, read_memory_file, is_expired,
        MEMORY_DIR, CATEGORY_DIR_MAP,
        compute_weight, resolve_conflict,
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
        "emphasis": fm.get("emphasis", False),
        "mention_count": fm.get("mention_count", 0),
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
    执行加权二级检索：总目录粗筛 → 独立文件精读

    检索排序遵循加权检索规范：
      分类1(project): 时间时效性(近期优先) > 用户强调/标记重点 > 常规记录
      分类2(habit): 用户强调/明确要求 > 时间时效性(最新优先) > 次要偏好
      分类3(skill): 用户强调/反复提及(mention_count>=3) > 其余全部

    补充约束：
      - 同一分类内，高优先级记忆必须优先纳入上下文，分配更高注意力权重
      - 低优先级记忆仅作辅助参考，不可覆盖、抵消高权重记忆内容
      - 若出现记忆冲突，直接采信层级权重更高的信息

    参数:
        query: 检索查询词或自然语言问题
        category_filter: 类别过滤 habit/skill/project，None=不过滤
        tag_filter: 标签过滤列表
        high_priority_only: 是否仅返回高优先级条目
        memory_dir: 自定义记忆目录

    返回:
        [{"file_path", "entry_id", "summary", "content_snippet",
          "score", "weight", "priority", "tags", "emphasis", "mention_count"}]
    """
    tag_filter = tag_filter or []
    results = []
    mem_dir = memory_dir or MEMORY_DIR

    # === 第一级：总目录粗筛 ===
    index_fm = read_memory_index(memory_dir=mem_dir)
    candidate_entries = []

    for entry_info in index_fm.get("entries", []):
        if not isinstance(entry_info, dict):
            continue

        # 类别过滤
        if category_filter and entry_info.get("category") != category_filter:
            continue

        keyword_score = 0
        query_lower = query.lower()
        summary = entry_info.get("summary", "")
        entry_tags = entry_info.get("tags", [])
        entry_priority = entry_info.get("priority", "low")

        # 摘要匹配
        if query and any(qw in summary.lower() for qw in query_lower.split()):
            keyword_score += 3

        # 标签匹配
        if query:
            for tag in entry_tags:
                if any(qw in tag.lower() for qw in query_lower.split()):
                    keyword_score += 2

        # tag_filter 过滤
        if tag_filter and not any(tf in entry_tags for tf in tag_filter):
            continue

        # 高优过滤
        if high_priority_only and entry_priority != "high":
            continue

        # 无匹配且非空查询时跳过
        if keyword_score == 0 and query:
            continue

        # 计算加权检索综合权重
        category = entry_info.get("category", "")
        emphasis = entry_info.get("emphasis", False)
        mention_count = entry_info.get("mention_count", 0)
        date_str = entry_info.get("last_modified") or entry_info.get("date")
        expires_str = entry_info.get("expires")

        weight = compute_weight(
            category=category,
            priority=entry_priority,
            emphasis=emphasis,
            mention_count=mention_count,
            date_str=date_str,
            keyword_score=keyword_score,
            expires_str=expires_str,
        )

        candidate_entries.append((entry_info, keyword_score, weight))

    # 按综合权重排序（高权重优先）
    candidate_entries.sort(key=lambda x: x[2], reverse=True)
    candidate_entries = candidate_entries[:10]

    # === 第二级：读取独立文件获取完整内容 ===
    for entry_info, keyword_score, weight in candidate_entries:
        file_rel_path = entry_info.get("path", "")
        file_abs_path = mem_dir / file_rel_path

        if not file_abs_path.exists():
            continue

        fm, body = read_memory_file(file_abs_path)

        # 从文件 front matter 中读取 emphasis 和 mention_count
        fm_emphasis = fm.get("emphasis", False)
        fm_mention_count = fm.get("mention_count", 0)

        # 用文件级别的 emphasis/mention_count 重新精确计算权重
        fm_category = fm.get("category", entry_info.get("category", ""))
        fm_priority = fm.get("priority", entry_info.get("priority", "medium"))
        fm_date = fm.get("date", entry_info.get("last_modified"))
        fm_expires = fm.get("expires")

        final_weight = compute_weight(
            category=fm_category,
            priority=fm_priority,
            emphasis=fm_emphasis,
            mention_count=fm_mention_count,
            date_str=fm_date,
            keyword_score=keyword_score,
            expires_str=fm_expires,
        )

        # 提取内容片段
        content_snippet = body.strip()
        if len(content_snippet) > 300:
            content_snippet = content_snippet[:300] + "..."

        results.append({
            "file_path": file_rel_path,
            "entry_id": entry_info.get("entry_id"),
            "category": fm_category,
            "summary": entry_info.get("summary", ""),
            "content_snippet": content_snippet,
            "score": keyword_score,
            "weight": final_weight,
            "priority": fm_priority,
            "tags": entry_info.get("tags", []),
            "emphasis": fm_emphasis,
            "mention_count": fm_mention_count,
            "date": entry_info.get("last_modified") or fm.get("date"),
        })

    # 按综合权重排序返回（高权重优先）
    results = resolve_conflict(results)
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
                print(f"找到 {len(results)} 条相关记忆（按加权权重排序）:\n")
                for i, r in enumerate(results, 1):
                    emp_mark = " [强调]" if r.get("emphasis") else ""
                    mc_mark = f" [提及{r.get('mention_count',0)}次]" if r.get("mention_count", 0) > 0 else ""
                    print(f"[{i}] ({r['priority']}) {r['summary']}{emp_mark}{mc_mark}")
                    print(f"    文件: {r['file_path']} | ID: {r['entry_id']} | 权重: {r['weight']} | 匹配分: {r['score']}\n")
    else:
        parser.print_help()
