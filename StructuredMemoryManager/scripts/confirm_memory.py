#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - confirm_memory 工具方法
===================================================
确认或更新记忆的有效性、保鲜期和优先级。
可独立调用：python scripts/confirm_memory.py <file_path> <entry_id> <action> [--expires ...] [--priority ...]
"""

import sys
import json
import argparse
from pathlib import Path

# 导入共享基础模块
from ._base import (
    read_memory_file, write_memory_file, now_iso,
    MEMORY_DIR
)


def confirm_memory(
    file_path: str,
    entry_id: str,
    action: str,
    new_expires: str = None,
    new_priority: str = None,
    memory_dir: Path = None
) -> dict:
    """
    确认或更新记忆状态。

    参数:
        file_path: 目标文件路径（相对于memory目录）
        entry_id: 条目ID (YYYY-MM-DD-HH-MM-NNN)
        action: 操作类型
            - confirm: 确认永不过期
            - extend: 延长有效期（需提供new_expires）
            - upgrade: 升级为高优先级
            - downgrade: 降级为低优先级
        new_expires: 新过期日期 (extend时必填)
        new_priority: 新优先级 (upgrade/downgrade时必填)
        memory_dir: 自定义记忆目录

    返回:
        {"success": True/False, "message": "..."}
    """
    mem_dir = memory_dir or MEMORY_DIR
    abs_path = mem_dir / file_path

    if not abs_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    fm, body = read_memory_file(abs_path)
    entries = fm.get("internal_index", fm.get("decision_log", []))

    # 查找目标条目
    target_entry = None
    target_idx = -1
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
            target_entry = entry
            target_idx = i
            break

    if target_entry is None:
        return {"success": False, "error": f"条目不存在: {entry_id}"}

    # 执行操作
    now = now_iso()

    if action == "confirm":
        target_entry["expires"] = None  # 确认后永不过期
        message = f"条目 {entry_id} 已确认为永久有效"

    elif action == "extend":
        if not new_expires:
            return {"success": False, "error": "extend操作需要new_expires参数"}
        target_entry["expires"] = new_expires
        message = f"条目 {entry_id} 有效期已延长至 {new_expires}"

    elif action == "upgrade":
        target_entry["priority"] = "high"
        # 加入高优标签
        ptags = set(fm.get("priority_tags", []) or [])
        ptags.update(target_entry.get("tags", []))
        fm["priority_tags"] = list(ptags)
        message = f"条目 {entry_id} 已升级为高优先级"

    elif action == "downgrade":
        target_entry["priority"] = "low"
        message = f"条目 {entry_id} 已降级为低优先级"

    else:
        return {"success": False, "error": f"未知操作: {action}，有效值为 confirm/extend/upgrade/downgrade"}

    # 更新修改时间
    fm["last_modified"] = now
    entries[target_idx] = target_entry

    # 写回文件
    write_memory_file(abs_path, fm, body)

    return {
        "success": True,
        "message": message,
        "entry_id": entry_id,
        "action": action,
        "updated_at": now
    }


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 确认/更新记忆")
    parser.add_argument("file_path", help="目标文件路径（相对memory目录）")
    parser.add_argument("entry_id", help="条目ID")
    parser.add_argument("action", choices=["confirm", "extend", "upgrade", "downgrade"],
                        help="操作类型")
    parser.add_argument("--expires", "-e", default=None, help="新过期日期 (extend时必填)")
    parser.add_argument("--priority", "-p", default=None, help="新优先级 (upgrade/downgrade)")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    result = confirm_memory(
        file_path=args.file_path,
        entry_id=args.entry_id,
        action=args.action,
        new_expires=args.expires,
        new_priority=args.priority
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
