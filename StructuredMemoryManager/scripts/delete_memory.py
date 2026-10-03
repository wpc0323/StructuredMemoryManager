#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - delete_memory 工具方法
================================================
删除记忆。默认软删除：文件移入该类别下的 deleted/ 子目录（可恢复），
总目录索引与向量库同步移除，检索不再命中。
--hard 时永久删除文件。

记忆系统必须能"遗忘"：错误的、过时的、被用户否认的记忆应及时删除，
而不是永远占着检索权重。
可独立调用：python scripts/delete_memory.py <file_path> [--hard]
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_file, read_memory_index, write_memory_index, now_iso,
        MEMORY_DIR, memory_lock, resolve_within_memory_dir,
        relpath_posix, same_relpath, is_vector_available
    )
    from .vector_store import delete_memory_vector
except ImportError:
    from _base import (
        read_memory_file, read_memory_index, write_memory_index, now_iso,
        MEMORY_DIR, memory_lock, resolve_within_memory_dir,
        relpath_posix, same_relpath, is_vector_available
    )
    from vector_store import delete_memory_vector


def delete_memory(
    file_path: str,
    hard: bool = False,
    memory_dir: Path = None
) -> dict:
    """
    删除一条记忆（按文件为单位）。

    参数:
        file_path: 目标文件路径（相对于memory目录）
        hard: True 永久删除文件；False 移入 deleted/ 子目录（软删除，可手动恢复）
        memory_dir: 自定义记忆目录

    返回:
        {"success": True/False, "action": "soft"/"hard", "file_path": ...,
         "removed_entries": N, "message": "..."}
    """
    mem_dir = memory_dir or MEMORY_DIR
    abs_path = resolve_within_memory_dir(file_path, mem_dir)
    if abs_path is None:
        return {"success": False, "error": f"非法路径（越出记忆目录）: {file_path}"}
    if abs_path.name == "memory_index.md":
        return {"success": False, "error": "禁止删除总目录索引文件 memory_index.md"}
    if not hard and "deleted" in abs_path.parts:
        return {"success": False, "error": "目标已在 deleted/ 回收区，如需永久删除请使用 --hard"}
    if not abs_path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    with memory_lock(mem_dir):
        fm, _ = read_memory_file(abs_path)
        target_rel = relpath_posix(abs_path, mem_dir)

        # 从总目录移除指向该文件的所有条目（project 文件可能对应多条）
        index_fm = read_memory_index(memory_dir=mem_dir)
        entries = index_fm.get("entries", [])
        kept = []
        removed = 0
        removed_ids = set()
        if fm.get("entry_id"):
            removed_ids.add(fm["entry_id"])
        for entry in entries:
            if isinstance(entry, dict) and same_relpath(entry.get("path", ""), target_rel):
                removed += 1
                if entry.get("entry_id"):
                    removed_ids.add(entry["entry_id"])
            else:
                kept.append(entry)

        if hard:
            abs_path.unlink()
            action = "hard"
            message = f"已永久删除 {target_rel}"
        else:
            deleted_dir = abs_path.parent / "deleted"
            deleted_dir.mkdir(parents=True, exist_ok=True)
            dest = deleted_dir / abs_path.name
            if dest.exists():
                # 同名文件已存在时追加时间戳避免覆盖
                dest = deleted_dir / f"{abs_path.stem}_{datetime.now().strftime('%H%M%S')}{abs_path.suffix}"
            abs_path.replace(dest)
            action = "soft"
            message = f"已将 {target_rel} 移入 deleted/（可手动移回恢复；--hard 可永久删除）"

        index_fm["entries"] = kept
        index_fm["last_modified"] = now_iso()
        write_memory_index(index_fm, memory_dir=mem_dir)

        # 同步从向量库移除（可选，chromadb 未安装时跳过）
        vector_warning = None
        if is_vector_available():
            for entry_id in removed_ids:
                vector_result = delete_memory_vector(entry_id=entry_id, memory_dir=mem_dir)
                if not vector_result.get("success") and not vector_result.get("skipped"):
                    vector_warning = vector_result.get("error", "未知错误")

    result = {
        "success": True,
        "action": action,
        "file_path": target_rel,
        "removed_entries": removed,
        "message": message,
    }
    if vector_warning:
        result["vector_warning"] = vector_warning
    return result


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 删除记忆")
    parser.add_argument("file_path", help="目标文件路径（相对memory目录）")
    parser.add_argument("--hard", action="store_true", help="永久删除（默认软删除到 deleted/）")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()

    result = delete_memory(file_path=args.file_path, hard=args.hard)

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
