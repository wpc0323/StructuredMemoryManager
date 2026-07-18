#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - confirm_memory 工具方法
===================================================
确认或更新记忆的有效性、保鲜期和优先级。
每条记忆为独立文件，直接修改对应文件的 front matter。
可独立调用：python scripts/confirm_memory.py <file_path> <entry_id> <action> [--expires ...] [--priority ...]
"""

import sys
import json
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_file, write_memory_file, now_iso,
        read_memory_index, write_memory_index, MEMORY_DIR
    )
except ImportError:
    from _base import (
        read_memory_file, write_memory_file, now_iso,
        read_memory_index, write_memory_index, MEMORY_DIR
    )


def confirm_memory(
    file_path: str,
    entry_id: str,
    action: str,
    new_expires: str = None,
    new_priority: str = None,
    emphasis: bool = None,
    mention_count: int = None,
    memory_dir: Path = None
) -> dict:
    """
    确认或更新记忆状态。
    直接修改对应记忆文件的 front matter。

    参数:
        file_path: 目标文件路径（相对于memory目录）
        entry_id: 条目ID (YYYY-MM-DD-HH-MM-NNN)
        action: 操作类型
            - confirm: 确认永不过期
            - extend: 延长有效期（需提供new_expires）
            - upgrade: 升级为高优先级
            - downgrade: 降级为低优先级
            - emphasize: 标记为用户主动强调/重点
            - de_emphasize: 取消强调标记
            - bump_mention: 增加提及次数
        new_expires: 新过期日期 (extend时必填)
        new_priority: 新优先级 (upgrade/downgrade时必填)
        emphasis: 强调标记 (emphasize/de_emphasize时使用)
        mention_count: 提及次数 (bump_mention时使用)
        memory_dir: 自定义记忆目录

    返回:
        {"success": True/False, "message": "..."}
    """
    mem_dir = memory_dir or MEMORY_DIR
    abs_path = mem_dir / file_path

    if not abs_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    fm, body = read_memory_file(abs_path)

    # 验证 entry_id 匹配
    if fm.get("entry_id") != entry_id:
        return {"success": False, "error": f"文件中的 entry_id ({fm.get('entry_id')}) 与请求的 ({entry_id}) 不匹配"}

    # 执行操作
    now = now_iso()

    if action == "confirm":
        fm["expires"] = None
        message = f"条目 {entry_id} 已确认为永久有效"

    elif action == "extend":
        if not new_expires:
            return {"success": False, "error": "extend操作需要new_expires参数"}
        fm["expires"] = new_expires
        message = f"条目 {entry_id} 有效期已延长至 {new_expires}"

    elif action == "upgrade":
        fm["priority"] = "high"
        message = f"条目 {entry_id} 已升级为高优先级"

    elif action == "downgrade":
        fm["priority"] = "low"
        message = f"条目 {entry_id} 已降级为低优先级"

    elif action == "emphasize":
        fm["emphasis"] = True
        message = f"条目 {entry_id} 已标记为用户主动强调/重点"

    elif action == "de_emphasize":
        fm["emphasis"] = False
        message = f"条目 {entry_id} 已取消强调标记"

    elif action == "bump_mention":
        current = fm.get("mention_count", 0)
        if mention_count is not None:
            fm["mention_count"] = mention_count
        else:
            fm["mention_count"] = current + 1
        message = f"条目 {entry_id} 提及次数已更新为 {fm['mention_count']}"

    else:
        return {"success": False, "error": f"未知操作: {action}，有效值为 confirm/extend/upgrade/downgrade/emphasize/de_emphasize/bump_mention"}

    # 更新修改时间
    fm["last_modified"] = now

    # 写回文件
    write_memory_file(abs_path, fm, body)

    # 同步更新总目录
    index_fm = read_memory_index(memory_dir=mem_dir)
    for entry in index_fm.get("entries", []):
        if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
            entry["priority"] = fm.get("priority", entry.get("priority"))
            entry["last_modified"] = now
            # 同步 emphasis 和 mention_count
            if "emphasis" in fm:
                entry["emphasis"] = fm["emphasis"]
            if "mention_count" in fm:
                entry["mention_count"] = fm["mention_count"]
            if action == "confirm":
                entry["expires"] = None
            elif action == "extend" and new_expires:
                entry["expires"] = new_expires
            break
    write_memory_index(index_fm, memory_dir=mem_dir)

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
    parser.add_argument("action", choices=["confirm", "extend", "upgrade", "downgrade", "emphasize", "de_emphasize", "bump_mention"],
                        help="操作类型")
    parser.add_argument("--expires", "-e", default=None, help="新过期日期 (extend时必填)")
    parser.add_argument("--priority", "-p", default=None, help="新优先级 (upgrade/downgrade)")
    parser.add_argument("--mention-count", "-m", type=int, default=None, help="提及次数 (bump_mention时使用)")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    result = confirm_memory(
        file_path=args.file_path,
        entry_id=args.entry_id,
        action=args.action,
        new_expires=args.expires,
        new_priority=args.priority,
        mention_count=args.mention_count
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
