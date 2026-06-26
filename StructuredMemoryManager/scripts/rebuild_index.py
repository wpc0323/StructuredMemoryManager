#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - rebuild_index 工具方法
==================================================
根据指定文件的正文内容全量重建其YAML内部索引。
可独立调用：python scripts/rebuild_index.py <file_path>
"""

import sys
import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 导入共享基础模块
from ._base import (
    read_memory_file, write_memory_file, now_iso,
    MEMORY_DIR
)


def rebuild_index(file_path: str, memory_dir: Path = None) -> dict:
    """
    根据正文内容全量重建 YAML internal_index。

    参数:
        file_path: 目标文件路径（相对于memory目录）
        memory_dir: 自定义记忆目录

    返回:
        {"success": True/False, "message": "...", "entries_count": N}
    """
    mem_dir = memory_dir or MEMORY_DIR
    abs_path = mem_dir / file_path

    if not abs_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    fm, body = read_memory_file(abs_path)

    # 解析正文中的所有条目
    new_index = _parse_body_to_index(body)

    # 保留原有元数据，只替换internal_index
    old_count = len(fm.get("internal_index", []))
    fm["internal_index"] = new_index
    fm["last_modified"] = now_iso()

    # 从新索引中提取所有高优标签
    all_high_tags = set()
    for entry in new_index:
        if isinstance(entry, dict) and entry.get("priority") == "high":
            all_high_tags.update(entry.get("tags", []))
    if all_high_tags:
        existing_ptags = set(fm.get("priority_tags", []) or [])
        existing_ptags.update(all_high_tags)
        fm["priority_tags"] = list(existing_ptags)

    # 写回文件
    write_memory_file(abs_path, fm, body)

    return {
        "success": True,
        "message": f"索引重建完成: {old_count} → {len(new_index)} 条",
        "file_path": file_path,
        "entries_count": len(new_index),
        "rebuilt_at": now_iso()
    }


def _parse_body_to_index(body: str) -> List[Dict[str, Any]]:
    """
    从正文解析出所有条目，生成新的 internal_index。

    解析规则：
    - 以 ### 开头的行作为条目分隔符
    - 提取 **ID:**、**优先级:**、**标签:**、**过期:** 元信息行
    - 用后续非分隔内容作为摘要来源
    """
    entries = []
    current_entry = None

    lines = body.split('\n')
    for line in lines:
        stripped = line.strip()

        # 检测新条目标题
        header_match = re.match(r'^###\s+(.+)$', stripped)
        if header_match:
            # 保存上一个条目
            if current_entry and current_entry.get("summary"):
                entries.append(current_entry)

            current_entry = {
                "date": _extract_date_from_header(header_match.group(1)),
                "priority": "medium",
                "summary": "",
                "tags": [],
                "expires": None,
                "entry_id": ""
            }
            continue

        if current_entry is None:
            continue

        # 解析元信息行
        id_match = re.match(r'^\*\*ID:\*\*\s*`(.+?)`', stripped)
        if id_match:
            current_entry["entry_id"] = id_match.group(1)
            continue

        prio_match = re.match(r'^\*\*优先级:\*\*\s*(\w+)', stripped)
        if prio_match:
            current_entry["priority"] = prio_match.group(1)
            continue

        tags_match = re.match(r'^\*\*标签:\*\*\s*(.+)', stripped)
        if tags_match:
            raw_tags = tags_match.group(1)
            if raw_tags != "无":
                current_entry["tags"] = [t.strip() for t in raw_tags.split(",")]
            continue

        exp_match = re.match(r'^\*\*过期:\*\*\s*(.+)', stripped)
        if exp_match:
            val = exp_match.group(1).strip()
            current_entry["expires"] = val if val != "永不过期" else None
            continue

        # 跳过分隔线和空元信息
        if stripped in ("---", "") or stripped.startswith("**"):
            continue

        # 收集摘要文本
        if current_entry.get("summary", "") == "" and stripped:
            clean_text = re.sub(r'[#*_`\[\](){}]', '', stripped)
            if len(clean_text) > 5:
                current_entry["summary"] = clean_text[:80]
            elif current_entry["summary"]:
                current_entry["summary"] += " " + clean_text

    # 保存最后一个条目
    if current_entry and current_entry.get("summary"):
        entries.append(current_entry)

    return entries


def _extract_date_from_header(header_text: str) -> str:
    """从 ### 标题中提取日期"""
    # 格式: ### 2026-06-24 15:30 或类似
    date_match = re.search(r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2})', header_text)
    if date_match:
        return date_match.group(1).replace(' ', 'T')
    return now_iso()


def batch_rebuild_all(memory_dir: Path = None) -> dict:
    """批量重建所有记忆文件的索引"""
    mem_dir = memory_dir or MEMORY_DIR
    results = []
    total_entries = 0

    # 遍历memory目录下所有.md文件
    for md_file in mem_dir.rglob("*.md"):
        rel_path = str(md_file.relative_to(mem_dir))
        # 跳过归档和索引文件本身
        if "archive" in rel_path or md_file.name == "memory_index.md":
            continue

        result = rebuild_index(rel_path, memory_dir=mem_dir)
        results.append({
            "file": rel_path,
            "success": result["success"],
            "entries": result.get("entries_count", 0)
        })
        if result["success"]:
            total_entries += result.get("entries_count", 0)

    return {
        "success": True,
        "processed_files": len(results),
        "total_entries": total_entries,
        "details": results
    }


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 重建索引")
    parser.add_argument("file_path", nargs="?", default=None, help="目标文件路径（--all时省略）")
    parser.add_argument("--all", "-a", action="store_true", help="批量重建所有文件")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    if args.all:
        result = batch_rebuild_all()
    elif args.file_path:
        result = rebuild_index(args.file_path)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
