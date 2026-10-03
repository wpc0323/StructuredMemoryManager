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

import json
import argparse
from pathlib import Path

# 支持独立运行和包导入
try:
    from ._base import (
        read_memory_index, read_memory_file, write_memory_file,
        write_memory_index, now_iso, is_expired,
        MEMORY_DIR, CATEGORY_DIR_MAP,
        compute_weight, resolve_conflict, is_vector_available,
        resolve_within_memory_dir, memory_lock, same_relpath,
        RELATED_EXPANSION_LIMIT,
    )
    from .vector_store import query_memory_vector, list_all_vector_memories, update_memory_metadata
except ImportError:
    from _base import (
        read_memory_index, read_memory_file, write_memory_file,
        write_memory_index, now_iso, is_expired,
        MEMORY_DIR, CATEGORY_DIR_MAP,
        compute_weight, resolve_conflict, is_vector_available,
        resolve_within_memory_dir, memory_lock, same_relpath,
        RELATED_EXPANSION_LIMIT,
    )
    from vector_store import query_memory_vector, list_all_vector_memories, update_memory_metadata


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
    abs_path = resolve_within_memory_dir(file_path, mem_dir)
    if abs_path is None:
        return {"success": False, "error": f"非法路径（越出记忆目录）: {file_path}"}

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
    memory_dir: Path = None,
    use_vector: bool = True,
    track_access: bool = True,
    expand_related: bool = True,
) -> list:
    """
    执行加权二级检索：总目录粗筛 → 独立文件精读

    检索模式:
      1. 向量模式（默认，chromadb 可用时）:
         - 非空 query: 语义相似度检索 → 按权重综合排序
         - 空 query: 从向量库列出全部 → 按权重排序
      2. 关键字模式（降级，chromadb 不可用 或 use_vector=False）:
         - 现有逻辑：总目录关键字匹配 → 独立文件精读

    检索排序遵循加权检索规范：
      分类1(project): 时间时效性(指数衰减) > 用户强调/标记重点 > 常规记录
      分类2(habit): 用户强调/明确要求 > 时间时效性(指数衰减) > 次要偏好
      分类3(skill): 用户强调/反复提及(mention_count>=3) > 其余全部

    后处理（v3.3）:
      - track_access: 命中条目 access_count +1 并写回（热度反馈回路）
      - expand_related: 按 related_files 附加关联记忆摘要
      - 已被取代（superseded_by 非空）的条目不参与检索

    参数:
        query: 检索查询词或自然语言问题
        category_filter: 类别过滤 habit/skill/project，None=不过滤
        tag_filter: 标签过滤列表
        high_priority_only: 是否仅返回高优先级条目
        memory_dir: 自定义记忆目录
        use_vector: 是否启用向量检索（True 优先，False 强制关键字）
        track_access: 是否回写命中计数（热度反馈回路）
        expand_related: 是否展开关联记忆

    返回:
        [{"file_path", "entry_id", "summary", "content_snippet",
          "score", "weight", "priority", "tags", "emphasis", "mention_count",
          "related"(expand_related 时), "similarity"(向量模式)}]
    """
    tag_filter = tag_filter or []
    mem_dir = memory_dir or MEMORY_DIR

    # 判断是否启用向量检索
    vector_enabled = use_vector and is_vector_available()

    # ============ 向量检索模式 ============
    if vector_enabled:
        results = _search_via_vector(
            query=query,
            category_filter=category_filter,
            tag_filter=tag_filter,
            high_priority_only=high_priority_only,
            memory_dir=mem_dir,
        )
        if not results:
            # 向量库为空或查询失败（如索引未同步、嵌入模型缺失）时，
            # 自动降级到关键字检索，避免"chromadb 已装但检索恒为空"。
            results = _search_via_keyword(
                query=query,
                category_filter=category_filter,
                tag_filter=tag_filter,
                high_priority_only=high_priority_only,
                memory_dir=mem_dir,
            )
    else:
        # ============ 关键字检索模式（降级） ============
        results = _search_via_keyword(
            query=query,
            category_filter=category_filter,
            tag_filter=tag_filter,
            high_priority_only=high_priority_only,
            memory_dir=mem_dir,
        )

    # 后处理：热度反馈回路 + 关联扩展（任何失败不影响检索结果本身）
    if results and track_access:
        _track_access(results, mem_dir)
    if results and expand_related:
        results = _expand_related(results, mem_dir)
    return results


def _track_access(results: list, mem_dir: Path):
    """
    检索命中回写（热度反馈回路）：
    结果条目的 access_count +1、last_accessed 更新，同步总目录索引与向量库元数据。
    权重公式用 access_count 计算检索热度加成——"被频繁命中的记忆"获得更高权重。
    尽力而为：任何失败都静默吞掉，不影响检索结果。
    """
    try:
        now = now_iso()
        vector_updates = []  # (entry_id, access_count)
        with memory_lock(mem_dir):
            index_fm = read_memory_index(memory_dir=mem_dir)
            index_changed = False
            for r in results:
                rel = r.get("file_path", "")
                if not rel:
                    continue
                abs_path = resolve_within_memory_dir(rel, mem_dir)
                if abs_path is None or not abs_path.exists():
                    continue
                fm, body = read_memory_file(abs_path)
                if not fm:
                    continue
                fm["access_count"] = int(fm.get("access_count", 0) or 0) + 1
                fm["last_accessed"] = now
                write_memory_file(abs_path, fm, body)
                if r.get("entry_id"):
                    vector_updates.append((r["entry_id"], fm["access_count"]))
                for entry in index_fm.get("entries", []):
                    # project 文件可能对应多条索引行，全部同步
                    if isinstance(entry, dict) and same_relpath(entry.get("path", ""), rel):
                        entry["access_count"] = fm["access_count"]
                        entry["last_accessed"] = now
                        index_changed = True
            if index_changed:
                index_fm["last_modified"] = now
                write_memory_index(index_fm, memory_dir=mem_dir)
        if is_vector_available():
            for entry_id, count in vector_updates:
                update_memory_metadata(
                    entry_id=entry_id,
                    metadata_updates={"access_count": count, "last_accessed": now},
                    memory_dir=mem_dir,
                )
    except Exception:
        pass


def _expand_related(results: list, mem_dir: Path) -> list:
    """
    关联扩展：按条目的 related_files 附加关联记忆的摘要。
    已出现在主结果中的路径不重复展开；每条最多展开 RELATED_EXPANSION_LIMIT 条。
    """
    try:
        index_fm = read_memory_index(memory_dir=mem_dir)
        by_path = {}
        for e in index_fm.get("entries", []):
            if isinstance(e, dict) and e.get("path"):
                by_path[str(e["path"]).replace("\\", "/")] = e
        seen = {str(r.get("file_path", "")).replace("\\", "/") for r in results}
        for r in results:
            related_raw = r.pop("related_files", None) or []
            related = []
            for rel in related_raw:
                if len(related) >= RELATED_EXPANSION_LIMIT:
                    break
                rel_norm = str(rel).replace("\\", "/")
                if rel_norm in seen:
                    continue
                entry = by_path.get(rel_norm)
                if not entry:
                    continue
                related.append({
                    "file_path": rel_norm,
                    "summary": entry.get("summary", ""),
                    "category": entry.get("category", ""),
                    "priority": entry.get("priority", ""),
                })
                seen.add(rel_norm)
            if related:
                r["related"] = related
    except Exception:
        pass
    return results


def _build_where_filter(category_filter: str = None, high_priority_only: bool = False) -> dict:
    """构建 ChromaDB where 过滤条件"""
    conditions = []
    if category_filter:
        conditions.append({"category": category_filter})
    if high_priority_only:
        conditions.append({"priority": "high"})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _apply_post_filters(entries: list, tag_filter: list, high_priority_only: bool) -> list:
    """对向量库返回的结果应用 tag_filter（ChromaDB 不直接支持 list 标签过滤），
    并过滤已被新记忆取代（superseded_by 非空）的条目"""
    filtered = []
    for e in entries:
        # 已被取代的条目不参与检索
        if e.get("superseded_by"):
            continue
        # tag 过滤（任一匹配）
        if tag_filter:
            entry_tags = e.get("tags", [])
            if not any(tf in entry_tags for tf in tag_filter):
                continue
        # 高优过滤（向量库查询已过滤，这里二次保险）
        if high_priority_only and e.get("priority") != "high":
            continue
        filtered.append(e)
    return filtered


def _search_via_vector(
    query: str,
    category_filter: str = None,
    tag_filter: list = None,
    high_priority_only: bool = False,
    memory_dir: Path = None,
) -> list:
    """向量检索模式：用语义相似度找候选，再用 compute_weight 综合排序"""
    tag_filter = tag_filter or []

    where = _build_where_filter(category_filter, high_priority_only)

    if query and query.strip():
        # 非空查询：语义检索 top 20
        candidates = query_memory_vector(
            query=query,
            n_results=20,
            where_filter=where,
            memory_dir=memory_dir,
        )
    else:
        # 空查询：列出全部
        candidates = list_all_vector_memories(
            where_filter=where,
            memory_dir=memory_dir,
        )

    # 应用 tag_filter（向量库不直接支持）与 superseded 过滤
    candidates = _apply_post_filters(candidates, tag_filter, high_priority_only)

    # 用 compute_weight 综合排序
    # 把 similarity 转换为 keyword_score 的等价值（similarity 0~1 → 0~10分）
    results = []
    for c in candidates:
        similarity = c.get("similarity", 0)
        # 将语义相似度转化为加分（最高+10）
        semantic_score = similarity * 10

        weight = compute_weight(
            category=c.get("category", ""),
            priority=c.get("priority", "medium"),
            emphasis=c.get("emphasis", False),
            mention_count=c.get("mention_count", 0),
            date_str=c.get("date"),
            keyword_score=semantic_score,
            expires_str=c.get("expires"),
            access_count=c.get("access_count", 0),
        )

        results.append({
            "file_path": c.get("file_path", ""),
            "entry_id": c.get("entry_id"),
            "category": c.get("category"),
            "summary": c.get("summary", ""),
            "content_snippet": c.get("content_snippet", ""),
            "score": round(semantic_score, 2),
            "weight": weight,
            "priority": c.get("priority"),
            "tags": c.get("tags", []),
            "emphasis": c.get("emphasis", False),
            "mention_count": c.get("mention_count", 0),
            "date": c.get("date"),
            "related_files": c.get("related_files", []),
            "similarity": round(similarity, 4),
        })

    results = resolve_conflict(results)
    return results[:10]


def _search_via_keyword(
    query: str,
    category_filter: str = None,
    tag_filter: list = None,
    high_priority_only: bool = False,
    memory_dir: Path = None,
) -> list:
    """关键字检索模式（原逻辑，作为降级方案）"""
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

        # 已被新记忆取代（supersede）的旧条目不参与检索
        if entry_info.get("superseded_by"):
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
            access_count=entry_info.get("access_count", 0),
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
            access_count=fm.get("access_count", 0),
            superseded=bool(fm.get("superseded_by")),
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
            "related_files": fm.get("related_files") or [],
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
    search_parser.add_argument("query", nargs="?", default="", help="检索查询词")
    search_parser.add_argument("--category", "-c", choices=["habit", "skill", "project"],
                        help="类别过滤")
    search_parser.add_argument("--tags", "-t", default="", help="标签过滤，逗号分隔")
    search_parser.add_argument("--high-priority", action="store_true", help="仅高优先级")
    search_parser.add_argument("--no-vector", action="store_true",
                        help="禁用向量检索，强制使用关键字匹配")

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
            high_priority_only=args.high_priority,
            use_vector=not args.no_vector,
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
