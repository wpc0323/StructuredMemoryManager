#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - 统一命令入口 (cli.py)
================================================
将所有工具方法统一到一个入口脚本，简化 Agent 的 Shell 调用。

用法:
  python cli.py add    -c <category> --content <text> [options]
  python cli.py search <query> [options]
  python cli.py read   <file_path>
  python cli.py confirm <file_path> <entry_id> <action> [options]
  python cli.py rebuild

所有命令支持 --json 参数输出结构化 JSON。
"""

import sys
import json
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from .add_memory import add_memory
    from .search_memory import search_memory, read_memory
    from .confirm_memory import confirm_memory
    from .rebuild_index import rebuild_index
except ImportError:
    from add_memory import add_memory
    from search_memory import search_memory, read_memory
    from confirm_memory import confirm_memory
    from rebuild_index import rebuild_index


def _parse_tags(tags_str: str) -> list:
    """解析逗号分隔的标签字符串"""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def cmd_add(args) -> dict:
    """执行 add_memory 命令"""
    return add_memory(
        category=args.category,
        content=args.content,
        priority=args.priority,
        tags=_parse_tags(args.tags),
        expires=args.expires,
        related=_parse_tags(args.related) if args.related else None,
        project_name=args.project_name,
        emphasis=args.emphasis,
        mention_count=args.mention_count,
    )


def cmd_search(args) -> list:
    """执行 search_memory 命令"""
    return search_memory(
        query=args.query,
        category_filter=args.category,
        tag_filter=_parse_tags(args.tags),
        high_priority_only=args.high_priority,
    )


def cmd_read(args) -> dict:
    """执行 read_memory 命令"""
    return read_memory(file_path=args.file_path)


def cmd_confirm(args) -> dict:
    """执行 confirm_memory 命令"""
    return confirm_memory(
        file_path=args.file_path,
        entry_id=args.entry_id,
        action=args.action,
        new_expires=args.expires,
        new_priority=args.priority,
        mention_count=args.mention_count,
    )


def cmd_rebuild(args) -> dict:
    """执行 rebuild_index 命令"""
    return rebuild_index()


def _add_json_flag(sub_parser):
    """为每个子命令添加 --json 标志"""
    sub_parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")


def main():
    parser = argparse.ArgumentParser(
        prog="smm",
        description="StructuredMemoryManager - 结构化长期记忆管理工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── add ──────────────────────────────────────────
    p_add = subparsers.add_parser("add", help="添加一条新记忆")
    p_add.add_argument("-c", "--category", required=True,
                       choices=["habit", "skill", "project"],
                       help="记忆类别: habit(习惯偏好) / skill(技能方法) / project(项目详情)")
    p_add.add_argument("--content", required=True,
                       help="记忆正文内容，支持 Markdown 格式")
    p_add.add_argument("-p", "--priority", default="medium",
                       choices=["high", "medium", "low"],
                       help="优先级 (默认: medium)")
    p_add.add_argument("-t", "--tags", default="",
                       help="标签列表，逗号分隔 (如: React,性能优化)")
    p_add.add_argument("-e", "--expires", default=None,
                       help="过期日期，ISO 8601 格式 (如: 2027-12-31)")
    p_add.add_argument("-r", "--related", default=None,
                       help="关联文件路径，逗号分隔")
    p_add.add_argument("--project-name", default=None,
                       help="项目名称 (category=project 时必填)")
    p_add.add_argument("--emphasis", action="store_true",
                       help="标记为用户主动强调/重点 (影响加权检索权重)")
    p_add.add_argument("--mention-count", type=int, default=0,
                       help="提及次数 (skill 类别，>=3 视为反复提及)")
    _add_json_flag(p_add)

    # ── search ───────────────────────────────────────
    p_search = subparsers.add_parser("search", help="检索记忆 (加权二级检索)")
    p_search.add_argument("query", nargs="?", default="",
                          help="检索查询词或自然语言问题 (省略或空字符串列出全部)")
    p_search.add_argument("--category", default=None,
                          choices=["habit", "skill", "project"],
                          help="类别过滤")
    p_search.add_argument("-t", "--tags", default="",
                          help="标签过滤，逗号分隔")
    p_search.add_argument("--high-priority", action="store_true",
                          help="仅返回高优先级条目")
    _add_json_flag(p_search)

    # ── read ─────────────────────────────────────────
    p_read = subparsers.add_parser("read", help="读取单条记忆的完整内容")
    p_read.add_argument("file_path",
                        help="目标文件路径 (相对于 memory 目录，如 habits/xxx.md)")
    _add_json_flag(p_read)

    # ── confirm ──────────────────────────────────────
    p_confirm = subparsers.add_parser("confirm", help="确认/更新记忆状态")
    p_confirm.add_argument("file_path",
                           help="目标文件路径 (相对于 memory 目录)")
    p_confirm.add_argument("entry_id",
                           help="条目 ID (格式: YYYY-MM-DD-HH-MM-NNN)")
    p_confirm.add_argument("action",
                           choices=["confirm", "extend", "upgrade", "downgrade",
                                    "emphasize", "de_emphasize", "bump_mention"],
                           help="操作类型")
    p_confirm.add_argument("-e", "--expires", default=None,
                           help="新过期日期 (extend 时必填)")
    p_confirm.add_argument("-p", "--priority", default=None,
                           help="新优先级 (upgrade/downgrade 时可选)")
    p_confirm.add_argument("-m", "--mention-count", type=int, default=None,
                           help="提及次数 (bump_mention 时可选，默认当前值+1)")
    _add_json_flag(p_confirm)

    # ── rebuild ──────────────────────────────────────
    p_rebuild = subparsers.add_parser("rebuild", help="全量重建总目录索引")
    _add_json_flag(p_rebuild)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 分发命令
    dispatch = {
        "add": cmd_add,
        "search": cmd_search,
        "read": cmd_read,
        "confirm": cmd_confirm,
        "rebuild": cmd_rebuild,
    }

    result = dispatch[args.command](args)

    # 输出
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if isinstance(result, list):
            if not result:
                print("未找到相关记忆。")
            else:
                print(f"找到 {len(result)} 条记忆（按加权权重排序）:\n")
                for i, r in enumerate(result, 1):
                    emp = " [强调]" if r.get("emphasis") else ""
                    mc = f" [提及{r.get('mention_count',0)}次]" if r.get("mention_count", 0) > 0 else ""
                    print(f"[{i}] ({r.get('priority','?')}) {r.get('summary','')}{emp}{mc}")
                    print(f"    文件: {r.get('file_path','')} | ID: {r.get('entry_id','')} "
                          f"| 权重: {r.get('weight',0):.0f} | 匹配分: {r.get('score',0)}\n")
        else:
            print(result)


if __name__ == "__main__":
    main()
