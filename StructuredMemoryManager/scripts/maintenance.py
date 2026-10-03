#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - maintenance 记忆维护检查
==================================================
只读扫描记忆库，列出需要人工/Agent 介入的条目：
  - expired:          已过保鲜期，需 confirm / extend / downgrade
  - archive_candidates: low 优先级且超过归档年龄的条目
  - stale:            medium 优先级且长期未更新（> STALE_DAYS）的条目
  - missing_files:    索引中存在但文件缺失的条目（提示 rebuild）

让记忆的保鲜期体系可被执行，而不是只在权重计算里默默扣分。
可独立调用：python scripts/maintenance.py [--json]
"""

import sys
import json
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_index, read_memory_file, is_expired,
        days_since_or_none, resolve_within_memory_dir, same_relpath,
        MEMORY_DIR, ARCHIVE_AGE_DAYS, STALE_DAYS, get_memory_stats
    )
except ImportError:
    from _base import (
        read_memory_index, read_memory_file, is_expired,
        days_since_or_none, resolve_within_memory_dir, same_relpath,
        MEMORY_DIR, ARCHIVE_AGE_DAYS, STALE_DAYS, get_memory_stats
    )

MAX_LIST_SIZE = 50  # 每类清单最多返回条数，完整数量见 summary


def _item(file_rel: str, entry: dict, fm: dict, extra: dict = None) -> dict:
    item = {
        "file_path": file_rel,
        "entry_id": fm.get("entry_id", entry.get("entry_id", "")),
        "category": fm.get("category", entry.get("category", "")),
        "priority": fm.get("priority", entry.get("priority", "")),
        "summary": fm.get("summary", entry.get("summary", "")),
    }
    if extra:
        item.update(extra)
    return item


def maintenance(memory_dir: Path = None) -> dict:
    """
    扫描记忆库，返回需要维护的条目清单（只读，不加锁不修改文件）。

    返回:
        {"success": True, "expired": [...], "archive_candidates": [...],
         "stale": [...], "missing_files": [...],
         "summary": {"expired": N, ...}, "hint": "..."}
    """
    mem_dir = memory_dir or MEMORY_DIR
    expired = []
    archive_candidates = []
    stale = []
    missing_files = []

    index_fm = read_memory_index(memory_dir=mem_dir)
    for entry in index_fm.get("entries", []):
        if not isinstance(entry, dict):
            continue
        file_rel = entry.get("path", "")
        abs_path = resolve_within_memory_dir(file_rel, mem_dir)
        if abs_path is None or not abs_path.exists():
            missing_files.append({"path": file_rel, "entry_id": entry.get("entry_id", "")})
            continue

        fm, _ = read_memory_file(abs_path)
        if not fm:
            continue

        # 已过期 → 建议确认/延长/降级
        expires = fm.get("expires")
        if expires and is_expired(expires):
            expired.append(_item(file_rel, entry, fm, {"expires": expires}))

        date_str = fm.get("date") or entry.get("last_modified")
        date_days = days_since_or_none(date_str)
        modified_days = days_since_or_none(fm.get("last_modified") or date_str)
        in_archive = "archive" in str(file_rel).replace("\\", "/").split("/")

        # 归档候选：low 优先级且超过归档年龄（归档流程本身会处理，这里仅供预览）
        if (fm.get("priority") == "low" and not in_archive
                and date_days is not None and date_days > ARCHIVE_AGE_DAYS):
            archive_candidates.append(_item(file_rel, entry, fm, {"date": date_str}))

        # 长期未更新：medium 优先级且超过保鲜确认期（system.md 5.1 的行为约定）
        if (fm.get("priority") == "medium"
                and modified_days is not None and modified_days > STALE_DAYS):
            stale.append(_item(file_rel, entry, fm, {"last_modified": fm.get("last_modified")}))

    expired.sort(key=lambda x: x.get("expires") or "")
    archive_candidates.sort(key=lambda x: x.get("date") or "", reverse=True)

    stats = get_memory_stats(memory_dir=mem_dir)
    file_total = sum(c["active_files"] + c["archived_files"] for c in stats["categories"].values())
    hint = None
    if stats["index_entries"] == 0 and file_total > 0:
        hint = "索引为空但存在记忆文件，建议执行 rebuild 重建索引"
    elif missing_files:
        hint = f"索引中有 {len(missing_files)} 条指向缺失文件，建议执行 rebuild 修复"

    return {
        "success": True,
        "expired": expired[:MAX_LIST_SIZE],
        "archive_candidates": archive_candidates[:MAX_LIST_SIZE],
        "stale": stale[:MAX_LIST_SIZE],
        "missing_files": missing_files[:MAX_LIST_SIZE],
        "summary": {
            "expired": len(expired),
            "archive_candidates": len(archive_candidates),
            "stale": len(stale),
            "missing_files": len(missing_files),
            "index_entries": stats["index_entries"],
        },
        "hint": hint,
    }


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 记忆维护检查")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()
    result = maintenance()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result["summary"]
        print(f"记忆维护检查: 过期 {s['expired']} 条 | 归档候选 {s['archive_candidates']} 条 "
              f"| 长期未更新 {s['stale']} 条 | 索引缺失文件 {s['missing_files']} 条")
        for title, key in (("已过期（建议 confirm/extend）", "expired"),
                           ("归档候选（low 且超龄）", "archive_candidates"),
                           ("长期未更新（medium 超180天）", "stale")):
            if result[key]:
                print(f"\n{title}:")
                for it in result[key]:
                    print(f"  - {it['file_path']}  {it['summary']}")
        if result.get("hint"):
            print(f"\n提示: {result['hint']}")
