#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - add_memory 工具方法
==============================================
添加一条新记忆并自动维护索引。
每条记忆生成一个独立文件，按类别存入子目录。
可独立调用：python scripts/add_memory.py --category habit --content "..." [--priority high] [--tags tag1,tag2]
"""

import sys
import json
import re
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        get_entry_file_path, read_memory_file, write_memory_file,
        read_memory_index, write_memory_index,
        now_iso, now_date_str, generate_entry_id, MEMORY_DIR,
        ARCHIVE_THRESHOLD, ARCHIVE_AGE_DAYS, ARCHIVE_AGE_DAYS_FALLBACK,
        CATEGORY_DIR_MAP, days_since, is_vector_available,
        memory_lock, relpath_posix, same_relpath, normalize_text_key,
        DEDUP_SIMILARITY, AUTO_LINK_MIN_SHARED_TAGS, AUTO_LINK_MAX_LINKS
    )
    from .vector_store import add_memory_vector, find_similar_memories
except ImportError:
    from _base import (
        get_entry_file_path, read_memory_file, write_memory_file,
        read_memory_index, write_memory_index,
        now_iso, now_date_str, generate_entry_id, MEMORY_DIR,
        ARCHIVE_THRESHOLD, ARCHIVE_AGE_DAYS, ARCHIVE_AGE_DAYS_FALLBACK,
        CATEGORY_DIR_MAP, days_since, is_vector_available,
        memory_lock, relpath_posix, same_relpath, normalize_text_key,
        DEDUP_SIMILARITY, AUTO_LINK_MIN_SHARED_TAGS, AUTO_LINK_MAX_LINKS
    )
    from vector_store import add_memory_vector, find_similar_memories


def _generate_summary(content: str, max_len: int = 80) -> str:
    """从内容生成简短摘要"""
    text = re.sub(r'[#*_`\[\](){}]', '', content)
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _update_index_for_entry(file_rel_path: str, category: str, summary: str,
                             priority: str, tags: list, entry_id: str,
                             project_name: str = None,
                             emphasis: bool = False, mention_count: int = 0,
                             memory_dir=None):
    """更新总目录中该条目的记录"""
    index_fm = read_memory_index(memory_dir=memory_dir)
    entries_list = index_fm.get("entries", [])

    entry_data = {
        "path": file_rel_path,
        "category": category,
        "summary": summary,
        "priority": priority,
        "tags": tags,
        "entry_id": entry_id,
        "last_modified": now_iso(),
        "emphasis": emphasis,
    }

    # skill 类别记录提及次数
    if category == "skill" and mention_count > 0:
        entry_data["mention_count"] = mention_count

    if category == "project" and project_name:
        entry_data["title"] = project_name

    # 查找是否已存在同 entry_id 的记录
    existing_idx = None
    for i, e in enumerate(entries_list):
        if isinstance(e, dict) and e.get("entry_id") == entry_id:
            existing_idx = i
            break

    if existing_idx is not None:
        entries_list[existing_idx] = entry_data
    else:
        entries_list.insert(0, entry_data)

    index_fm["entries"] = entries_list
    index_fm["last_modified"] = now_iso()
    write_memory_index(index_fm, memory_dir=memory_dir)


def _check_archiving(category: str, memory_dir: Path = None) -> dict:
    """
    检查并执行归档（当类别目录下文件数超过阈值时）
    将低优先级且过期的条目文件移入 archive 子目录，并同步更新总目录索引
    """
    mem_dir = memory_dir or MEMORY_DIR
    cat_dir = mem_dir / CATEGORY_DIR_MAP.get(category, category)
    if not cat_dir.exists():
        return {"archived": False, "count": 0}

    # 统计该类别下的文件数
    md_files = list(cat_dir.glob("*.md"))
    if len(md_files) <= ARCHIVE_THRESHOLD:
        return {"archived": False, "count": 0}

    # 筛选低优且旧的文件
    archive_dir = cat_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    archived_count = 0
    archived_paths = []  # 记录被归档的文件相对路径

    def _archive_round(files, age_threshold):
        """执行一轮归档"""
        count = 0
        moved = []
        for md_file in files:
            if not md_file.exists():
                continue
            fm, _ = read_memory_file(md_file)
            if not fm:
                continue
            priority = fm.get("priority", "low")
            date_str = fm.get("date", "")
            if priority == "low" and days_since(date_str) > age_threshold:
                dest = archive_dir / md_file.name
                md_file.rename(dest)
                count += 1
                try:
                    moved.append(relpath_posix(md_file, mem_dir))
                except ValueError:
                    pass
        return count, moved

    # 第一轮：90天阈值
    archived_count, archived_paths = _archive_round(md_files, ARCHIVE_AGE_DAYS)

    # 第二轮：若归档后仍超阈值，用60天阈值
    remaining = list(cat_dir.glob("*.md"))
    if len(remaining) > ARCHIVE_THRESHOLD:
        round2_count, round2_paths = _archive_round(remaining, ARCHIVE_AGE_DAYS_FALLBACK)
        archived_count += round2_count
        archived_paths.extend(round2_paths)

    # 同步更新总目录索引中对应条目的路径
    if archived_paths:
        index_fm = read_memory_index(memory_dir=mem_dir)
        cat_dir_name = CATEGORY_DIR_MAP.get(category, category)
        for old_rel_path in archived_paths:
            for entry in index_fm.get("entries", []):
                if isinstance(entry, dict) and same_relpath(entry.get("path", ""), old_rel_path):
                    # 更新路径指向 archive 子目录
                    file_name = Path(old_rel_path).name
                    entry["path"] = f"{cat_dir_name}/archive/{file_name}"
        write_memory_index(index_fm, memory_dir=mem_dir)

    return {"archived": archived_count > 0, "count": archived_count}


def add_memory(
    category: str,
    content: str,
    priority: str = "medium",
    tags: list = None,
    expires: str = None,
    related: list = None,
    project_name: str = None,
    emphasis: bool = False,
    mention_count: int = 0,
    allow_dedup: bool = True,
    memory_dir: Path = None
) -> dict:
    """
    添加一条新记忆，生成独立文件并更新索引。

    默认开启去重：新内容与已有 habit/skill 记忆重复（归一化后精确匹配，
    或向量相似度 >= DEDUP_SIMILARITY）时不新建文件，而是合并进已有记忆
    （无损追加正文，并按需提升 mention_count/emphasis/优先级）。
    传 allow_dedup=False（CLI 的 --no-dedup）强制新建独立文件。

    参数:
        category: habit/skill/project
        content: 记忆正文(Markdown)
        priority: high/medium/low
        tags: 标签列表
        expires: 过期日期(ISO)或None
        related: 关联文件列表
        project_name: 项目名称(category=project时必填)
        emphasis: 是否被用户主动强调/标记重点（影响加权检索权重）
        mention_count: 被提及的次数（skill类别使用，>=3视为反复提及）
        allow_dedup: 是否允许自动去重合并（False 强制新建）
        memory_dir: 自定义记忆目录(默认使用配置值)

    返回:
        {"success": True, "entry_id": "...", "file_path": "..."}
        去重合并时返回 {"success": True, "deduplicated": True, "merged_into": {...}}
    """
    mem_dir = memory_dir or MEMORY_DIR
    with memory_lock(mem_dir):
        return _add_memory_impl(
            category=category, content=content, priority=priority,
            tags=tags, expires=expires, related=related,
            project_name=project_name, emphasis=emphasis,
            mention_count=mention_count, allow_dedup=allow_dedup,
            mem_dir=mem_dir,
        )


def _scan_existing_entries(mem_dir: Path) -> list:
    """
    扫描所有类别目录（不含 archive/、deleted/ 子目录）下的记忆文件，
    返回供 entry_id 生成与去重匹配共用的条目信息列表。
    """
    dir_to_category = {v: k for k, v in CATEGORY_DIR_MAP.items()}
    entries = []
    for dir_name, category in dir_to_category.items():
        cat_dir = mem_dir / dir_name
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob("*.md"):
            fm, body = read_memory_file(f)
            if not fm or not fm.get("entry_id"):
                continue
            try:
                file_rel = relpath_posix(f, mem_dir)
            except ValueError:
                continue
            entries.append({
                "entry_id": fm["entry_id"],
                "category": fm.get("category") or category,
                "file_rel": file_rel,
                "summary": fm.get("summary", ""),
                "summary_norm": normalize_text_key(fm.get("summary", "")),
                "body": body,
                "body_norm": normalize_text_key(body),
                "tags": fm.get("tags") or [],
            })
    return entries


def _append_related(file_abs: Path, new_related: list):
    """向记忆文件的 related_files 追加路径（去重、POSIX 化），无变化时不重写文件"""
    fm, body = read_memory_file(file_abs)
    if not fm:
        return
    related = fm.get("related_files") or []
    if isinstance(related, str):
        related = [r.strip() for r in related.split(",") if r.strip()]
    related_norm = [str(r).replace("\\", "/") for r in related]
    changed = False
    for r in new_related:
        r_norm = str(r).replace("\\", "/")
        if r_norm not in related_norm:
            related_norm.append(r_norm)
            changed = True
    if changed:
        fm["related_files"] = related_norm
        write_memory_file(file_abs, fm, body)


def _auto_link_related(new_file_rel: str, tags: list,
                       existing_entries: list, mem_dir: Path) -> list:
    """
    标签自动互链：新记忆与共享标签数 >= AUTO_LINK_MIN_SHARED_TAGS 的已有记忆
    建立双向 related_files 关联（上限 AUTO_LINK_MAX_LINKS 条），
    构建记忆间的链接网络（A-MEM 式卡片盒的轻量实现）。
    返回与新记忆建立关联的已有记忆路径列表。
    """
    if not tags:
        return []
    tag_set = set(tags)
    matched = []
    for e in existing_entries:
        if len(matched) >= AUTO_LINK_MAX_LINKS:
            break
        shared = tag_set & set(e.get("tags") or [])
        if len(shared) >= AUTO_LINK_MIN_SHARED_TAGS:
            matched.append(e["file_rel"])
    if not matched:
        return []
    # 新记忆 → 已有记忆
    _append_related(mem_dir / new_file_rel, matched)
    # 已有记忆 → 新记忆（双向）
    for rel in matched:
        _append_related(mem_dir / rel, [new_file_rel])
    return matched


def _find_duplicate(existing_entries: list, category: str, content: str,
                    summary: str, mem_dir: Path):
    """
    查找与新内容重复的已有记忆（仅 habit/skill 参与去重，project 本身就是单文件追加）。
    两级匹配：
      1. 精确匹配：归一化后与已有摘要相同，或已包含在正文中
      2. 向量匹配：语义相似度 >= DEDUP_SIMILARITY（chromadb 可用时），
         且召回条目仍存在于文件扫描结果中（排除已归档/已删除的）
    """
    if category not in ("habit", "skill"):
        return None

    key = normalize_text_key(content)
    if key:
        for e in existing_entries:
            if e["category"] != category:
                continue
            if e["summary_norm"] == key or key in e["body_norm"]:
                return e

    if is_vector_available():
        res = find_similar_memories(
            f"{summary}\n{content}", n_results=5, category=category, memory_dir=mem_dir
        )
        if res.get("success") and not res.get("skipped"):
            scanned_ids = {e["entry_id"] for e in existing_entries if e["category"] == category}
            for m in res.get("matches", []):
                if m.get("similarity", 0) >= DEDUP_SIMILARITY and m.get("entry_id") in scanned_ids:
                    for e in existing_entries:
                        if e["entry_id"] == m["entry_id"] and e["category"] == category:
                            return e
    return None


_PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _merge_into_existing(existing: dict, content: str, category: str,
                         priority: str, emphasis: bool, mem_dir: Path) -> dict:
    """
    将新内容合并进已有记忆：无损追加正文，按需提升 mention_count（skill）、
    emphasis 和优先级，并同步总目录索引与向量库文档。
    """
    file_abs = mem_dir / existing["file_rel"]
    fm, body = read_memory_file(file_abs)
    now = now_iso()

    if category == "skill":
        fm["mention_count"] = int(fm.get("mention_count", 0) or 0) + 1
    if emphasis:
        fm["emphasis"] = True
    if _PRIORITY_ORDER.get(priority, 1) > _PRIORITY_ORDER.get(fm.get("priority", "medium"), 1):
        fm["priority"] = priority
    fm["last_modified"] = now

    # 内容已存在（逐字重复）时不重复追加，保证多次记录同一条偏好不会膨胀正文
    new_norm = normalize_text_key(content)
    if new_norm and new_norm not in normalize_text_key(body):
        body = body.rstrip() + "\n\n---\n\n" + content.strip() + "\n"
    write_memory_file(file_abs, fm, body)

    index_fm = read_memory_index(memory_dir=mem_dir)
    for entry in index_fm.get("entries", []):
        if isinstance(entry, dict) and same_relpath(entry.get("path", ""), existing["file_rel"]):
            entry["last_modified"] = now
            entry["emphasis"] = fm.get("emphasis", entry.get("emphasis", False))
            if "mention_count" in fm:
                entry["mention_count"] = fm["mention_count"]
    index_fm["last_modified"] = now
    write_memory_index(index_fm, memory_dir=mem_dir)

    if is_vector_available():
        add_memory_vector(
            entry_id=existing["entry_id"],
            file_path=existing["file_rel"],
            summary=fm.get("summary", ""),
            content=body.strip(),
            category=category,
            priority=fm.get("priority", "medium"),
            tags=fm.get("tags", []) or [],
            emphasis=fm.get("emphasis", False),
            mention_count=fm.get("mention_count", 0),
            date=fm.get("date", ""),
            expires=fm.get("expires"),
            memory_dir=mem_dir,
        )

    return {
        "success": True,
        "deduplicated": True,
        "merged_into": {"file_path": existing["file_rel"], "entry_id": existing["entry_id"]},
        "message": f"新内容与已有记忆高度相似，已合并至 {existing['file_rel']}（--no-dedup 可强制新建）",
    }


def _add_memory_impl(
    category: str,
    content: str,
    priority: str,
    tags: list,
    expires: str,
    related: list,
    project_name: str,
    emphasis: bool,
    mention_count: int,
    allow_dedup: bool,
    mem_dir: Path
) -> dict:
    tags = tags or []
    related = related or []

    # 1. 生成摘要
    summary = _generate_summary(content)

    # 2. 扫描已有记忆（entry_id 生成与去重共用一次扫描，避免跨类别ID冲突）
    existing_entries = _scan_existing_entries(mem_dir)
    existing_ids = [e["entry_id"] for e in existing_entries]

    # 3. 去重检查
    if allow_dedup:
        duplicate = _find_duplicate(existing_entries, category, content, summary, mem_dir)
        if duplicate:
            return _merge_into_existing(duplicate, content, category, priority, emphasis, mem_dir)

    entry_id = generate_entry_id(existing_ids)
    now = now_iso()
    date_header = now_date_str()

    # 4. 生成文件路径
    file_path = get_entry_file_path(category, entry_id, summary, project_name, memory_dir=mem_dir)

    # 5. 对于项目类型，如果文件已存在则追加
    if category == "project" and file_path.exists():
        fm, body = read_memory_file(file_path)
        # 在正文顶部追加新内容
        new_block = (
            f"### {summary}\n\n"
            f"**ID**: `{entry_id}`  \n"
            f"**时间**: {date_header}  \n"
            f"**优先级**: {priority}  \n"
            f"**标签**: {', '.join(tags) if tags else '无'}  \n"
            f"**过期**: {expires or '永不过期'}  \n\n"
            f"{content}\n\n"
            "---\n\n"
        )
        body = new_block + body
        fm["last_modified"] = now
        if "decision_log" not in fm:
            fm["decision_log"] = []
        fm["decision_log"].insert(0, {
            "date": now,
            "decision": summary,
            "entry_id": entry_id
        })
        write_memory_file(file_path, fm, body)
    else:
        # 4. 创建新的独立记忆文件
        fm = {
            "entry_id": entry_id,
            "date": now,
            "category": category,
            "priority": priority,
            "tags": tags,
            "summary": summary,
            "expires": expires,
            "related_files": related,
            "last_modified": now,
            "emphasis": emphasis,
        }

        # skill 类别记录提及次数
        if category == "skill" and mention_count > 0:
            fm["mention_count"] = mention_count

        if category == "project" and project_name:
            fm["project_name"] = project_name
            fm["status"] = "active"
            # 第一条决策也计入 decision_log（与 system.md 中的项目文件规范一致）
            fm["decision_log"] = [{
                "date": now,
                "decision": summary,
                "entry_id": entry_id,
            }]

        body = content + "\n"

        write_memory_file(file_path, fm, body)

    # 6. 更新总目录
    file_rel_path = relpath_posix(file_path, mem_dir)
    _update_index_for_entry(file_rel_path, category, summary, priority, tags, entry_id, project_name, emphasis, mention_count, memory_dir=mem_dir)

    # 6.2 标签自动互链：与共享标签的已有记忆建立双向 related_files 关联
    auto_linked = _auto_link_related(file_rel_path, tags, existing_entries, mem_dir)
    related_all = list(related) + auto_linked

    # 6.5 同步写入向量库（可选，chromadb 未安装时跳过）
    vector_notice = None
    if is_vector_available():
        vector_result = add_memory_vector(
            entry_id=entry_id,
            file_path=file_rel_path,
            summary=summary,
            content=content,
            category=category,
            priority=priority,
            tags=tags,
            emphasis=emphasis,
            mention_count=mention_count,
            date=now,
            expires=expires,
            related_files=related_all,
            access_count=0,
            memory_dir=mem_dir,
        )
        if not vector_result.get("success") and not vector_result.get("skipped"):
            vector_notice = f"向量库写入失败: {vector_result.get('error', '未知错误')}"

    # 7. 归档检查
    cat_dir = mem_dir / CATEGORY_DIR_MAP.get(category, category)
    if cat_dir.exists():
        file_count = len(list(cat_dir.glob("*.md")))
        if file_count > ARCHIVE_THRESHOLD:
            archive_result = _check_archiving(category, memory_dir=mem_dir)
            if archive_result["archived"]:
                result = {
                    "success": True,
                    "entry_id": entry_id,
                    "file_path": file_rel_path,
                    "archive_notice": f"已归档 {archive_result['count']} 条旧记忆"
                }
                if vector_notice:
                    result["vector_warning"] = vector_notice
                return result

    result = {
        "success": True,
        "entry_id": entry_id,
        "file_path": file_rel_path,
        "notice": "记忆已保存为独立文件"
    }
    if vector_notice:
        result["vector_warning"] = vector_notice
    return result


# ============================================================
# CLI 入口（支持独立运行）
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 添加记忆")
    parser.add_argument("--category", "-c", required=True, choices=["habit", "skill", "project"],
                        help="记忆类别")
    parser.add_argument("--content", required=True, help="记忆内容")
    parser.add_argument("--priority", "-p", default="medium", choices=["high", "medium", "low"],
                        help="优先级")
    parser.add_argument("--tags", "-t", default="", help="标签，逗号分隔")
    parser.add_argument("--expires", "-e", default=None, help="过期日期 ISO 8601")
    parser.add_argument("--project-name", default=None, help="项目名称(project类别必填)")
    parser.add_argument("--related", "-r", default=None, help="关联文件路径，逗号分隔")
    parser.add_argument("--emphasis", action="store_true", help="标记为用户主动强调/重点")
    parser.add_argument("--mention-count", type=int, default=0, help="提及次数(skill类别，>=3视为反复提及)")
    parser.add_argument("--no-dedup", action="store_true", help="禁用自动去重，强制新建独立文件")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")

    args = parser.parse_args()
    tags_list = [t.strip() for t in args.tags.split(",")] if args.tags else []
    related_list = [t.strip() for t in args.related.split(",")] if args.related else None

    result = add_memory(
        category=args.category,
        content=args.content,
        priority=args.priority,
        tags=tags_list,
        expires=args.expires,
        related=related_list,
        project_name=args.project_name,
        emphasis=args.emphasis,
        mention_count=args.mention_count,
        allow_dedup=not args.no_dedup
    )

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
