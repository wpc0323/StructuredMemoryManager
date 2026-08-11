#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - 嵌入模型下载工具
==========================================
从 HuggingFace 镜像 (hf-mirror.com) 下载 all-MiniLM-L6-v2 ONNX 模型，
存放到 ChromaDB 期望的目录，避免 ChromaDB 默认从 S3 下载（国内极慢）。

ChromaDB 的 ONNXMiniLM_L6_V2 在 _download_model_if_not_exists() 中会检查
以下 6 个文件是否存在于 DOWNLOAD_PATH/onnx/ 目录：
  - config.json
  - model.onnx
  - special_tokens_map.json
  - tokenizer_config.json
  - tokenizer.json
  - vocab.txt

若全部存在，则跳过下载。本脚本提前放好这些文件，让 ChromaDB 直接使用。

用法:
  python download_model.py              # 下载到默认位置（skill 目录下 .cache/）
  python download_model.py --check      # 仅检查文件是否已就绪
  python download_model.py --force      # 强制重新下载
"""

import os
import sys
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# 路径配置
# ============================================================
SKILL_ROOT = Path(__file__).parent.parent
CACHE_DIR = SKILL_ROOT / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"
ONNX_DIR = CACHE_DIR / "onnx"

# HuggingFace 镜像（国内快速）
HF_MIRROR = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
REPO_ID = "Xenova/all-MiniLM-L6-v2"

# 需要下载的 6 个文件（相对于 repo 根目录的路径）
REQUIRED_FILES = {
    "config.json": "config.json",
    "model.onnx": "onnx/model.onnx",               # ~86MB，主要文件
    "special_tokens_map.json": "special_tokens_map.json",
    "tokenizer_config.json": "tokenizer_config.json",
    "tokenizer.json": "tokenizer.json",
    "vocab.txt": "vocab.txt",
}


def build_url(repo_path: str) -> str:
    """构建 HuggingFace 镜像下载 URL"""
    return f"{HF_MIRROR}/{REPO_ID}/resolve/main/{repo_path}"


def check_files() -> dict:
    """检查所有必需文件是否已存在且非空"""
    result = {}
    for local_name in REQUIRED_FILES:
        fpath = ONNX_DIR / local_name
        if fpath.exists() and fpath.stat().st_size > 0:
            result[local_name] = fpath.stat().st_size
        else:
            result[local_name] = 0
    return result


def download_file(local_name: str, repo_path: str) -> tuple:
    """下载单个文件，返回 (local_name, success, size, error)"""
    url = build_url(repo_path)
    dest = ONNX_DIR / local_name
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StructuredMemoryManager/3.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        actual_size = dest.stat().st_size
        if actual_size > 0:
            return (local_name, True, actual_size, None)
        else:
            return (local_name, False, 0, "Downloaded file is empty")
    except Exception as e:
        return (local_name, False, 0, str(e))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="下载 all-MiniLM-L6-v2 ONNX 嵌入模型")
    parser.add_argument("--check", action="store_true", help="仅检查文件是否已就绪")
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    args = parser.parse_args()

    print(f"模型存放目录: {ONNX_DIR}")
    print(f"下载源: {HF_MIRROR}/{REPO_ID}")
    print()

    # 检查现有文件
    existing = check_files()
    all_present = all(v > 0 for v in existing.values())

    if args.check:
        print("=== 文件状态 ===")
        for name, size in existing.items():
            status = "✓" if size > 0 else "✗"
            size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size} B"
            print(f"  {status} {name}: {size_str}")
        print()
        if all_present:
            print("✓ 所有文件就绪，ChromaDB 可直接使用")
        else:
            print("✗ 缺少文件，需要下载")
        return

    if all_present and not args.force:
        print("✓ 所有文件已存在，无需下载（使用 --force 强制重下）")
        return

    # 清理旧文件（如果 --force）
    if args.force:
        for name in REQUIRED_FILES:
            fpath = ONNX_DIR / name
            if fpath.exists():
                fpath.unlink()
        print("已清理旧文件")

    ONNX_DIR.mkdir(parents=True, exist_ok=True)

    # 下载所有文件（model.onnx 单独下，其余并行）
    print("开始下载...")
    small_files = {k: v for k, v in REQUIRED_FILES.items() if k != "model.onnx"}

    # 先并行下载小文件
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(download_file, name, repo_path): name
            for name, repo_path in small_files.items()
        }
        for future in as_completed(futures):
            name, success, size, error = future.result()
            if success:
                print(f"  ✓ {name} ({size} bytes)")
            else:
                print(f"  ✗ {name}: {error}")

    # 再下载大文件 model.onnx
    print("  下载 model.onnx (~86MB)...")
    name, success, size, error = download_file("model.onnx", REQUIRED_FILES["model.onnx"])
    if success:
        print(f"  ✓ model.onnx ({size / 1024 / 1024:.1f} MB)")
    else:
        print(f"  ✗ model.onnx: {error}")

    # 最终检查
    print()
    existing = check_files()
    all_present = all(v > 0 for v in existing.values())
    if all_present:
        print("✓ 所有文件下载完成，ChromaDB 可直接使用")
    else:
        print("✗ 部分文件缺失，请重试")
        sys.exit(1)


if __name__ == "__main__":
    main()
