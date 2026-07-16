#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - rebuild_index 工具方法
==================================================
扫描所有记忆文件，重建总目录 memory_index.md 的索引。
可独立调用：python scripts/rebuild_index.py [--all]
"""

import sys
import json
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_file, write_memory_file, now_iso,
        read_memory_index, write_memory_index, MEMORY_DIR,
        CATEGORY_DIR_MAP
    )
except ImportError:
    from _base import (
        read_memory_file, write_memory_file, now_iso,
        read_memory_index, write_memory_index, MEMORY_DIR,
        CATEGORY_DIR_MAP
    )


def rebuild_index(memory_dir: Path = None) -> dict:
    """
    扫描所有记忆文件，重建总目录索引。

    参数:
        memory_dir: 自定义记忆目录

    返回:
        {"success": True, "message": "...", "entries_count": N}
    """
    mem_dir = memory_dir or MEMORY_DIR
    entries = []

    # 遍历所有类别子目录
    for category, dir_name in CATEGORY_DIR_MAP.items():
        cat_dir = mem_dir / dir_name
        if not cat_dir.exists():
            continue

        for md_file in cat_dir.rglob("*.md"):
            # 跳过归档子目录中的文件（但仍索引）
            rel_path = str(md_file.relative_to(mem_dir))

            fm, body = read_memory_file(md_file)
            if not fm or not fm.get("entry_id"):
                continue

            entry_data = {
                "path": rel_path,
                "category": fm.get("category", category),
                "summary": fm.get("summary", ""),
                "priority": fm.get("priority", "medium"),
                "tags": fm.get("tags", []),
                "entry_id": fm.get("entry_id", ""),
                "last_modified": fm.get("last_modified", now_iso()),
            }

            if category == "project" and fm.get("project_name"):
                entry_data["title"] = fm["project_name"]

            entries.append(entry_data)

    # 按修改时间倒序排列
    entries.sort(key=lambda e: e.get("last_modified", ""), reverse=True)

    # 写入总目录
    index_fm = read_memory_index()
    old_count = len(index_fm.get("entries", []))
    index_fm["entries"] = entries
    index_fm["last_modified"] = now_iso()
    write_memory_index(index_fm)

    return {
        "success": True,
        "message": f"索引重建完成: {old_count} → {len(entries)} 条",
        "entries_count": len(entries),
        "rebuilt_at": now_iso()
    }


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 重建索引")
    parser.add_argument("--all", "-a", action="store_true", help="重建全部索引")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    result = rebuild_index()

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
