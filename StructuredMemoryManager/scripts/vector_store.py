#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - vector_store 向量数据库封装
=====================================================
使用 ChromaDB 提供语义检索能力，替代纯关键字匹配。
所有操作都设计为"可选"，chromadb 未安装时自动降级。

存储设计:
  集合名: memories
  路径: {memory_dir}/vector_db/
  文档: "{summary}\n\n{content}"  (用于向量化)
  metadata:
    - entry_id (str)
    - file_path (str)
    - category (str)
    - priority (str)
    - tags (str, 逗号分隔，因 ChromaDB metadata 不支持 list)
    - emphasis (bool)
    - mention_count (int)
    - date (str, ISO 8601)
    - expires (str, 可空)

资源本地化:
  所有 ChromaDB/HuggingFace 缓存都下载到 {SKILL_ROOT}/.cache/，
  确保 skill 自包含、可打包迁移。
  - {SKILL_ROOT}/.cache/huggingface/  (嵌入模型缓存)
  - {SKILL_ROOT}/.cache/chroma/       (chromadb 运行时缓存)
"""

import os
import sys
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

# ============================================================
# 资源本地化：在导入 chromadb 之前设置缓存目录
# ============================================================
# SKILL_ROOT = StructuredMemoryManager/ 根目录
SKILL_ROOT = Path(__file__).parent.parent

# 所有缓存统一放在 skill 目录下的 .cache/
_LOCAL_CACHE_DIR = SKILL_ROOT / ".cache"
_LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# HuggingFace 模型缓存（all-MiniLM-L6-v2 嵌入模型约 79MB）
_HF_CACHE = _LOCAL_CACHE_DIR / "huggingface"
_HF_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_HF_CACHE))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_HF_CACHE / "hub"))
os.environ.setdefault("HF_HUB_CACHE", str(_HF_CACHE / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_HF_CACHE / "transformers"))

# ChromaDB 运行时缓存
_CHROMA_CACHE = _LOCAL_CACHE_DIR / "chroma"
_CHROMA_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CHROMA_CACHE_DIR", str(_CHROMA_CACHE))

# 国内用户可选：使用 hf-mirror.com 镜像加速下载（不强制，用户可自行覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 屏蔽 telemetry，避免网络请求
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# 现在才尝试导入 chromadb
try:
    import chromadb
    HAS_CHROMADB = True
    # ChromaDB 1.5.x 的 ONNXMiniLM_L6_V2 类硬编码了下载路径为
    # ~/.cache/chroma/onnx_models/，不读环境变量。
    # 这里 monkey-patch 类属性，把下载路径重定向到工作区。
    try:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import (
            ONNXMiniLM_L6_V2 as _OnnxEF,
        )
        _ONNX_DOWNLOAD_PATH = (
            _LOCAL_CACHE_DIR / "chroma" / "onnx_models" / _OnnxEF.MODEL_NAME
        )
        _ONNX_DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
        _OnnxEF.DOWNLOAD_PATH = _ONNX_DOWNLOAD_PATH
    except (ImportError, AttributeError):
        # 老版本 chromadb 无此类，或结构不同，跳过 patch
        pass
except ImportError:
    HAS_CHROMADB = False


# ============================================================
# 可用性检测
# ============================================================

def is_vector_available() -> bool:
    """检查向量检索是否可用"""
    return HAS_CHROMADB


def _get_collection(memory_dir: Path = None):
    """
    获取（或创建）ChromaDB collection。
    返回 (collection, error_msg)；失败时 collection=None。
    """
    if not HAS_CHROMADB:
        return None, "chromadb 未安装，请运行: pip install chromadb"

    try:
        from ._base import MEMORY_DIR
    except ImportError:
        from _base import MEMORY_DIR

    mem_dir = memory_dir or MEMORY_DIR
    vector_db_path = mem_dir / "vector_db"
    vector_db_path.mkdir(parents=True, exist_ok=True)

    try:
        client = chromadb.PersistentClient(path=str(vector_db_path))
        collection = client.get_or_create_collection(
            name="memories",
            metadata={"description": "StructuredMemoryManager 记忆语义索引"}
        )
        return collection, None
    except Exception as e:
        return None, f"ChromaDB 初始化失败: {e}"


# ============================================================
# 元数据构建
# ============================================================

def _build_metadata(entry_id: str, file_path: str, category: str,
                    priority: str, tags: list, emphasis: bool,
                    mention_count: int, date: str,
                    expires: Optional[str] = None) -> Dict[str, Any]:
    """
    构建 ChromaDB metadata。
    注意: ChromaDB metadata 只支持 str/int/float/bool，不支持 list。
    """
    md = {
        "entry_id": entry_id,
        "file_path": file_path,
        "category": category,
        "priority": priority,
        "tags": ",".join(tags) if isinstance(tags, list) else str(tags or ""),
        "emphasis": bool(emphasis),
        "mention_count": int(mention_count or 0),
        "date": date or "",
    }
    if expires is not None:
        md["expires"] = str(expires)
    return md


def _build_document(summary: str, content: str) -> str:
    """构建用于向量化的文档文本"""
    summary = (summary or "").strip()
    content = (content or "").strip()
    if not summary and not content:
        return ""
    if not content:
        return summary
    if not summary:
        return content
    return f"{summary}\n\n{content}"


# ============================================================
# 写入操作
# ============================================================

def add_memory_vector(
    entry_id: str,
    file_path: str,
    summary: str,
    content: str,
    category: str,
    priority: str = "medium",
    tags: list = None,
    emphasis: bool = False,
    mention_count: int = 0,
    date: str = None,
    expires: Optional[str] = None,
    memory_dir: Path = None
) -> dict:
    """
    将一条记忆添加（或更新）到向量库。
    若 entry_id 已存在，ChromaDB 的 upsert 会覆盖旧记录。

    返回:
        {"success": True/False, "skipped": bool, "error": str(失败时)}
    """
    if not HAS_CHROMADB:
        return {"success": True, "skipped": True, "reason": "chromadb 未安装"}

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return {"success": False, "skipped": False, "error": err}

    document = _build_document(summary, content)
    if not document:
        return {"success": True, "skipped": True, "reason": "空文档"}

    metadata = _build_metadata(
        entry_id=entry_id, file_path=file_path, category=category,
        priority=priority, tags=tags or [], emphasis=emphasis,
        mention_count=mention_count, date=date or "", expires=expires
    )

    try:
        collection.upsert(
            ids=[entry_id],
            documents=[document],
            metadatas=[metadata],
        )
        return {"success": True, "skipped": False}
    except Exception as e:
        return {"success": False, "skipped": False, "error": str(e)}


def update_memory_metadata(
    entry_id: str,
    metadata_updates: dict,
    memory_dir: Path = None
) -> dict:
    """
    更新向量库中某条记忆的 metadata（不改变文档内容）。
    用于 confirm_memory 的优先级/emphasis 等更新。

    参数:
        metadata_updates: 要更新的字段 dict（仅 metadata，不含 document）

    返回:
        {"success": True/False, "error": str}
    """
    if not HAS_CHROMADB:
        return {"success": True, "skipped": True, "reason": "chromadb 未安装"}

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return {"success": False, "error": err}

    try:
        # 先获取现有记录
        existing = collection.get(ids=[entry_id])
        if not existing or not existing.get("ids"):
            return {"success": True, "skipped": True, "reason": "向量库中无此条目"}

        current_metadata = existing.get("metadatas", [{}])[0] or {}
        # 合并更新
        for k, v in metadata_updates.items():
            if k == "tags" and isinstance(v, list):
                current_metadata["tags"] = ",".join(v)
            else:
                current_metadata[k] = v

        collection.update(
            ids=[entry_id],
            metadatas=[current_metadata],
        )
        return {"success": True, "skipped": False}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_memory_vector(entry_id: str, memory_dir: Path = None) -> dict:
    """从向量库删除一条记忆"""
    if not HAS_CHROMADB:
        return {"success": True, "skipped": True, "reason": "chromadb 未安装"}

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return {"success": False, "error": err}

    try:
        collection.delete(ids=[entry_id])
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# 检索操作
# ============================================================

def query_memory_vector(
    query: str,
    n_results: int = 20,
    where_filter: dict = None,
    memory_dir: Path = None
) -> List[Dict[str, Any]]:
    """
    语义检索：用查询词的向量在记忆库中找最相似的条目。

    参数:
        query: 自然语言查询
        n_results: 返回的最大候选数
        where_filter: ChromaDB metadata 过滤条件
            - {"category": "habit"} 精确匹配
            - {"priority": "high"} 精确匹配
            - {"$and": [...]} 组合条件
        memory_dir: 自定义记忆目录

    返回:
        [{"entry_id", "file_path", "category", "priority", "tags",
           "emphasis", "mention_count", "date", "expires",
           "summary", "content_snippet", "similarity"}]
        similarity: 0~1，越大越相似
    """
    if not HAS_CHROMADB:
        return []

    if not query or not query.strip():
        return []

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return []

    try:
        # 构建 where 过滤条件
        where = None
        if where_filter:
            where = where_filter

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
        }
        if where is not None:
            kwargs["where"] = where

        results = collection.query(**kwargs)
    except Exception as e:
        print(f"[vector_store] 查询失败: {e}", file=__import__('sys').stderr)
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    # 解析结果
    ids = results["ids"][0]
    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []
    distances = results.get("distances", [[]])[0] or []

    output = []
    for i, entry_id in enumerate(ids):
        doc = documents[i] if i < len(documents) else ""
        md = metadatas[i] if i < len(metadatas) else {}
        dist = distances[i] if i < len(distances) else 0.0

        # ChromaDB 默认使用余弦距离，distance 越小越相似
        # 转换为 similarity: similarity = 1 - distance/2 (近似)
        # 对于 L2 距离，用 1/(1+distance) 更稳健
        try:
            similarity = 1.0 / (1.0 + float(dist))
        except (ValueError, TypeError):
            similarity = 0.0

        # 从 document 还原 summary 和 content
        # document 格式: "{summary}\n\n{content}"
        if "\n\n" in doc:
            summary, content = doc.split("\n\n", 1)
        else:
            summary, content = doc, ""

        # 截断 content
        if len(content) > 300:
            content = content[:300] + "..."

        # 解析 tags
        tags_str = md.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        output.append({
            "entry_id": entry_id,
            "file_path": md.get("file_path", ""),
            "category": md.get("category", ""),
            "priority": md.get("priority", "medium"),
            "tags": tags,
            "emphasis": bool(md.get("emphasis", False)),
            "mention_count": int(md.get("mention_count", 0)),
            "date": md.get("date", ""),
            "expires": md.get("expires"),
            "summary": summary,
            "content_snippet": content,
            "similarity": similarity,
        })

    return output


def list_all_vector_memories(
    where_filter: dict = None,
    memory_dir: Path = None
) -> List[Dict[str, Any]]:
    """
    列出向量库中所有记忆（不带查询，用于空查询场景）。
    注意：ChromaDB 不支持"无条件返回全部"，这里用 get() 而非 query()。
    """
    if not HAS_CHROMADB:
        return []

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return []

    try:
        kwargs = {}
        if where_filter:
            kwargs["where"] = where_filter
        results = collection.get(**kwargs)
    except Exception as e:
        return []

    if not results or not results.get("ids"):
        return []

    ids = results["ids"]
    documents = results.get("documents", []) or []
    metadatas = results.get("metadatas", []) or []

    output = []
    for i, entry_id in enumerate(ids):
        doc = documents[i] if i < len(documents) else ""
        md = metadatas[i] if i < len(metadatas) else {}

        if "\n\n" in doc:
            summary, content = doc.split("\n\n", 1)
        else:
            summary, content = doc, ""

        if len(content) > 300:
            content = content[:300] + "..."

        tags_str = md.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        output.append({
            "entry_id": entry_id,
            "file_path": md.get("file_path", ""),
            "category": md.get("category", ""),
            "priority": md.get("priority", "medium"),
            "tags": tags,
            "emphasis": bool(md.get("emphasis", False)),
            "mention_count": int(md.get("mention_count", 0)),
            "date": md.get("date", ""),
            "expires": md.get("expires"),
            "summary": summary,
            "content_snippet": content,
            "similarity": 1.0,  # 无查询时无相似度
        })

    return output


# ============================================================
# 全量重建
# ============================================================

def rebuild_vector_store(entries: List[Dict[str, Any]], memory_dir: Path = None) -> dict:
    """
    全量重建向量库：删除旧集合，按 entries 重新写入。

    参数:
        entries: 来自 memory_index.md 的 entries 列表，每项含
                 path, category, summary, priority, tags, entry_id,
                 last_modified, emphasis, mention_count(可选), title(可选)

    返回:
        {"success": True/False, "count": N, "error": str(失败时)}
    """
    if not HAS_CHROMADB:
        return {"success": True, "skipped": True, "reason": "chromadb 未安装", "count": 0}

    try:
        from ._base import MEMORY_DIR, read_memory_file
    except ImportError:
        from _base import MEMORY_DIR, read_memory_file

    mem_dir = memory_dir or MEMORY_DIR

    # 删除旧集合
    try:
        import chromadb
        vector_db_path = mem_dir / "vector_db"
        client = chromadb.PersistentClient(path=str(vector_db_path))
        try:
            client.delete_collection(name="memories")
        except Exception:
            pass  # 集合不存在
        collection = client.get_or_create_collection(
            name="memories",
            metadata={"description": "StructuredMemoryManager 记忆语义索引"}
        )
    except Exception as e:
        return {"success": False, "error": f"重建集合失败: {e}", "count": 0}

    # 逐条写入
    success_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        file_rel_path = entry.get("path", "")
        if not file_rel_path:
            continue

        file_abs_path = mem_dir / file_rel_path
        if not file_abs_path.exists():
            continue

        # 从原文件读取完整内容
        fm, body = read_memory_file(file_abs_path)
        summary = fm.get("summary") or entry.get("summary", "")
        content = body.strip()

        entry_id = entry.get("entry_id") or fm.get("entry_id", "")
        if not entry_id:
            continue

        metadata = _build_metadata(
            entry_id=entry_id,
            file_path=file_rel_path,
            category=fm.get("category", entry.get("category", "")),
            priority=fm.get("priority", entry.get("priority", "medium")),
            tags=fm.get("tags", entry.get("tags", [])),
            emphasis=fm.get("emphasis", entry.get("emphasis", False)),
            mention_count=fm.get("mention_count", entry.get("mention_count", 0)),
            date=fm.get("date", entry.get("last_modified", "")),
            expires=fm.get("expires"),
        )

        document = _build_document(summary, content)
        if not document:
            continue

        try:
            collection.upsert(
                ids=[entry_id],
                documents=[document],
                metadatas=[metadata],
            )
            success_count += 1
        except Exception:
            continue

    return {"success": True, "count": success_count}


# ============================================================
# 状态查询
# ============================================================

def get_vector_store_stats(memory_dir: Path = None) -> dict:
    """获取向量库统计信息"""
    if not HAS_CHROMADB:
        return {"available": False, "reason": "chromadb 未安装"}

    collection, err = _get_collection(memory_dir)
    if collection is None:
        return {"available": False, "reason": err}

    try:
        count = collection.count()
        return {
            "available": True,
            "count": count,
            "collection_name": "memories",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


# ============================================================
# CLI 入口（独立测试用）
# ============================================================

if __name__ == "__main__":
    import sys
    import json
    import argparse

    parser = argparse.ArgumentParser(description="StructuredMemoryManager - 向量库工具")
    sub = parser.add_subparsers(dest="cmd")

    p_stats = sub.add_parser("stats", help="查看向量库状态")
    p_query = sub.add_parser("query", help="语义查询")
    p_query.add_argument("query", help="查询词")
    p_query.add_argument("-n", "--n-results", type=int, default=10)
    p_query.add_argument("--category", default=None)
    p_query.add_argument("--high-priority", action="store_true")

    p_rebuild = sub.add_parser("rebuild", help="从 memory_index.md 重建向量库")

    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.cmd == "stats":
        result = get_vector_store_stats()
    elif args.cmd == "query":
        where = None
        if args.category and args.high_priority:
            where = {"$and": [{"category": args.category}, {"priority": "high"}]}
        elif args.category:
            where = {"category": args.category}
        elif args.high_priority:
            where = {"priority": "high"}
        result = query_memory_vector(args.query, n_results=args.n_results, where_filter=where)
    elif args.cmd == "rebuild":
        try:
            from ._base import read_memory_index
        except ImportError:
            from _base import read_memory_index
        index = read_memory_index()
        result = rebuild_vector_store(index.get("entries", []))
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
