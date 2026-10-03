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
        read_memory_index, write_memory_index, MEMORY_DIR, is_vector_available,
        resolve_within_memory_dir, memory_lock
    )
    from .vector_store import update_memory_metadata
except ImportError:
    from _base import (
        read_memory_file, write_memory_file, now_iso,
        read_memory_index, write_memory_index, MEMORY_DIR, is_vector_available,
        resolve_within_memory_dir, memory_lock
    )
    from vector_store import update_memory_metadata


def confirm_memory(
    file_path: str,
    entry_id: str,
    action: str,
    new_expires: str = None,
    new_priority: str = None,
    mention_count: int = None,
    superseded_by: str = None,
    memory_dir: Path = None
) -> dict:
    """确认或更新记忆状态（带跨进程锁）。参数详见 _confirm_memory_impl。"""
    mem_dir = memory_dir or MEMORY_DIR
    with memory_lock(mem_dir):
        return _confirm_memory_impl(
            file_path=file_path, entry_id=entry_id, action=action,
            new_expires=new_expires, new_priority=new_priority,
            mention_count=mention_count, superseded_by=superseded_by,
            mem_dir=mem_dir,
        )


def _confirm_memory_impl(
    file_path: str,
    entry_id: str,
    action: str,
    new_expires: str = None,
    new_priority: str = None,
    mention_count: int = None,
    superseded_by: str = None,
    mem_dir: Path = None
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
            - upgrade: 升级优先级（默认升为high，可通过new_priority指定）
            - downgrade: 降级优先级（默认降为low，可通过new_priority指定）
            - emphasize: 标记为用户主动强调/重点
            - de_emphasize: 取消强调标记
            - bump_mention: 增加提及次数
            - supersede: 标记被新记忆取代（需提供superseded_by），自动降为low并退出检索
        new_expires: 新过期日期 (extend时必填)
        new_priority: 新优先级 (upgrade时默认"high"，downgrade时默认"low")
        mention_count: 提及次数 (bump_mention时使用，默认当前值+1)
        superseded_by: 取代本条目的新记忆路径 (supersede时必填)
        mem_dir: 已解析的记忆目录（由外层 confirm_memory 传入）

    返回:
        {"success": True/False, "message": "..."}
    """
    abs_path = resolve_within_memory_dir(file_path, mem_dir)
    if abs_path is None:
        return {"success": False, "error": f"非法路径（越出记忆目录）: {file_path}"}

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
        target_priority = new_priority if new_priority in ("high", "medium") else "high"
        fm["priority"] = target_priority
        message = f"条目 {entry_id} 已升级为 {target_priority} 优先级"

    elif action == "downgrade":
        target_priority = new_priority if new_priority in ("medium", "low") else "low"
        fm["priority"] = target_priority
        message = f"条目 {entry_id} 已降级为 {target_priority} 优先级"

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

    elif action == "supersede":
        # 冲突失效机制：用户更正偏好时，旧记忆标记被取代并降级，
        # 检索不再命中（历史保留，可通过 read 查看），避免新旧记忆竞争权重
        if not superseded_by:
            return {"success": False,
                    "error": "supersede 操作需要提供取代它的记忆路径（--superseded-by）"}
        fm["superseded_by"] = superseded_by
        fm["priority"] = "low"
        message = (f"条目 {entry_id} 已被 {superseded_by} 取代，"
                   f"自动降为 low 并在检索中排除")

    else:
        return {"success": False, "error": f"未知操作: {action}，有效值为 confirm/extend/upgrade/downgrade/emphasize/de_emphasize/bump_mention/supersede"}

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
            if action == "supersede" and fm.get("superseded_by"):
                entry["superseded_by"] = fm["superseded_by"]
            break
    write_memory_index(index_fm, memory_dir=mem_dir)

    # 同步更新向量库 metadata（可选）
    vector_warning = None
    if is_vector_available():
        metadata_updates = {"last_modified": now}
        # 根据 action 同步对应字段
        if action in ("upgrade", "downgrade"):
            metadata_updates["priority"] = fm.get("priority")
        elif action == "emphasize":
            metadata_updates["emphasis"] = True
        elif action == "de_emphasize":
            metadata_updates["emphasis"] = False
        elif action == "bump_mention":
            metadata_updates["mention_count"] = fm.get("mention_count", 0)
        elif action == "supersede":
            metadata_updates["superseded_by"] = fm.get("superseded_by", "")
            metadata_updates["priority"] = fm.get("priority")
        elif action == "confirm":
            metadata_updates["expires"] = ""
        elif action == "extend" and new_expires:
            metadata_updates["expires"] = str(new_expires)

        vector_result = update_memory_metadata(
            entry_id=entry_id,
            metadata_updates=metadata_updates,
            memory_dir=mem_dir,
        )
        if not vector_result.get("success") and not vector_result.get("skipped"):
            vector_warning = vector_result.get("error", "未知错误")

    result = {
        "success": True,
        "message": message,
        "entry_id": entry_id,
        "action": action,
        "updated_at": now
    }
    if vector_warning:
        result["vector_warning"] = vector_warning
    return result


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 确认/更新记忆")
    parser.add_argument("file_path", help="目标文件路径（相对memory目录）")
    parser.add_argument("entry_id", help="条目ID")
    parser.add_argument("action", choices=["confirm", "extend", "upgrade", "downgrade", "emphasize", "de_emphasize", "bump_mention", "supersede"],
                        help="操作类型")
    parser.add_argument("--expires", "-e", default=None, help="新过期日期 (extend时必填)")
    parser.add_argument("--priority", "-p", default=None, help="新优先级 (upgrade/downgrade)")
    parser.add_argument("--mention-count", "-m", type=int, default=None, help="提及次数 (bump_mention时使用)")
    parser.add_argument("--superseded-by", "-s", default=None, help="取代本条目的新记忆路径 (supersede时必填)")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    result = confirm_memory(
        file_path=args.file_path,
        entry_id=args.entry_id,
        action=args.action,
        new_expires=args.expires,
        new_priority=args.priority,
        mention_count=args.mention_count,
        superseded_by=args.superseded_by
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
