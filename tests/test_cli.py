"""CLI 端到端测试：通过子进程调用 cli.py，验证 SMM_MEMORY_DIR 环境变量与 JSON 输出"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parent.parent / "StructuredMemoryManager" / "scripts" / "cli.py"


def run_cli(args, mem_dir):
    env = {**os.environ, "SMM_MEMORY_DIR": str(mem_dir),
           "SMM_NO_VECTOR": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    return proc.stdout


@pytest.fixture
def mem_dir(tmp_path):
    return tmp_path / "memory"


def test_add_and_search_via_cli(mem_dir):
    out = run_cli(["add", "-c", "habit", "--content", "用户偏好深色主题",
                   "-p", "high", "-t", "UI风格", "--emphasis", "--json"], mem_dir)
    result = json.loads(out)
    assert result["success"] is True
    assert result["file_path"].startswith("habits")

    out = run_cli(["search", "深色主题", "--no-vector", "--json"], mem_dir)
    results = json.loads(out)
    assert len(results) == 1
    assert results[0]["priority"] == "high"
    assert results[0]["emphasis"] is True


def test_read_via_cli(mem_dir):
    run_cli(["add", "-c", "skill", "--content", "React Hooks优化模式", "--json"], mem_dir)
    results = json.loads(run_cli(["search", "React", "--no-vector", "--json"], mem_dir))
    out = run_cli(["read", results[0]["file_path"], "--json"], mem_dir)
    content = json.loads(out)
    assert "React Hooks优化模式" in content["content"]


def test_confirm_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "必须用中文回复", "--json"], mem_dir)
    results = json.loads(run_cli(["search", "中文", "--no-vector", "--json"], mem_dir))
    entry = results[0]
    out = run_cli(["confirm", entry["file_path"], entry["entry_id"],
                   "emphasize", "--json"], mem_dir)
    assert json.loads(out)["success"] is True


def test_rebuild_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "偏好一", "--json"], mem_dir)
    (mem_dir / "memory_index.md").unlink()
    out = run_cli(["rebuild", "--json"], mem_dir)
    result = json.loads(out)
    assert result["success"] is True
    assert result["entries_count"] == 1


def test_stats_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "偏好一", "--json"], mem_dir)
    out = run_cli(["stats", "--json"], mem_dir)
    stats = json.loads(out)
    assert stats["categories"]["habit"]["active_files"] == 1
    assert stats["index_entries"] == 1
    assert "vector_store" in stats
    assert stats["memory_dir"] == str(mem_dir)


def test_cli_env_var_isolation(mem_dir, tmp_path):
    """不同 SMM_MEMORY_DIR 之间记忆完全隔离"""
    other_dir = tmp_path / "other_memory"
    run_cli(["add", "-c", "habit", "--content", "第一套记忆", "--json"], mem_dir)
    out = run_cli(["search", "第一套记忆", "--no-vector", "--json"], other_dir)
    assert json.loads(out) == []


def test_delete_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "待删除记忆", "--json"], mem_dir)
    results = json.loads(run_cli(["search", "待删除", "--no-vector", "--json"], mem_dir))
    out = run_cli(["delete", results[0]["file_path"], "--json"], mem_dir)
    assert json.loads(out)["success"] is True
    assert json.loads(run_cli(["search", "待删除", "--no-vector", "--json"], mem_dir)) == []
    # 软删除后文件进入 deleted/ 且不被 rebuild 复活
    run_cli(["rebuild", "--json"], mem_dir)
    assert json.loads(run_cli(["stats", "--json"], mem_dir))["index_entries"] == 0


def test_maintenance_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "维护检查条目", "--json"], mem_dir)
    out = run_cli(["maintenance", "--json"], mem_dir)
    result = json.loads(out)
    assert result["success"] is True
    assert result["summary"]["index_entries"] == 1


def test_dedup_via_cli(mem_dir):
    run_cli(["add", "-c", "habit", "--content", "重复内容测试", "--json"], mem_dir)
    out = run_cli(["add", "-c", "habit", "--content", "重复内容测试", "--json"], mem_dir)
    assert json.loads(out).get("deduplicated") is True
    out2 = run_cli(["add", "-c", "habit", "--content", "重复内容测试",
                    "--no-dedup", "--json"], mem_dir)
    assert json.loads(out2).get("deduplicated") is None
