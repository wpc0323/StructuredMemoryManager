"""delete 命令测试：软删除/硬删除、索引与向量库同步、防误删"""

import pytest

import _base
import add_memory as add_mod
import search_memory as search_mod
import rebuild_index as rebuild_mod
import delete_memory as delete_mod
from delete_memory import delete_memory
from _base import get_memory_stats


@pytest.fixture(autouse=True)
def force_keyword_mode(monkeypatch):
    monkeypatch.setattr(_base, "HAS_CHROMADB", False)


@pytest.fixture
def mem_dir(tmp_path):
    d = tmp_path / "memory"
    _base.ensure_memory_dir(d)
    return d


def _add_one(mem_dir):
    return add_mod.add_memory(category="habit", content="用户偏好深色主题",
                              priority="high", tags=["UI"], memory_dir=mem_dir)


class TestSoftDelete:
    def test_soft_delete_moves_to_deleted_dir(self, mem_dir):
        r = _add_one(mem_dir)
        result = delete_memory(r["file_path"], memory_dir=mem_dir)
        assert result["success"] is True
        assert result["action"] == "soft"
        # 文件移入 deleted/ 子目录
        deleted_files = list((mem_dir / "habits" / "deleted").glob("*.md"))
        assert len(deleted_files) == 1
        # 原位置不再存在
        assert not (mem_dir / r["file_path"]).exists()

    def test_soft_delete_syncs_index(self, mem_dir):
        r = _add_one(mem_dir)
        delete_memory(r["file_path"], memory_dir=mem_dir)
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert index_fm["entries"] == []

    def test_soft_delete_content_not_searchable(self, mem_dir):
        r = _add_one(mem_dir)
        assert len(search_mod.search_memory("深色", memory_dir=mem_dir, use_vector=False)) == 1
        delete_memory(r["file_path"], memory_dir=mem_dir)
        assert search_mod.search_memory("深色", memory_dir=mem_dir, use_vector=False) == []

    def test_rebuild_does_not_resurrect_deleted(self, mem_dir):
        r = _add_one(mem_dir)
        delete_memory(r["file_path"], memory_dir=mem_dir)
        result = rebuild_mod.rebuild_index(memory_dir=mem_dir)
        assert result["entries_count"] == 0

    def test_stats_counts_deleted(self, mem_dir):
        r = _add_one(mem_dir)
        delete_memory(r["file_path"], memory_dir=mem_dir)
        stats = get_memory_stats(memory_dir=mem_dir)
        assert stats["categories"]["habit"]["deleted_files"] == 1
        assert stats["categories"]["habit"]["active_files"] == 0

    def test_delete_project_file_removes_all_entries(self, mem_dir):
        add_mod.add_memory(category="project", content="决策一", priority="high",
                           project_name="demo", memory_dir=mem_dir)
        add_mod.add_memory(category="project", content="决策二", priority="high",
                           project_name="demo", memory_dir=mem_dir)
        result = delete_memory("projects/demo.md", memory_dir=mem_dir)
        assert result["success"] is True
        assert result["removed_entries"] == 2
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert index_fm["entries"] == []


class TestHardDelete:
    def test_hard_delete_removes_file(self, mem_dir):
        r = _add_one(mem_dir)
        result = delete_memory(r["file_path"], hard=True, memory_dir=mem_dir)
        assert result["success"] is True
        assert result["action"] == "hard"
        assert not (mem_dir / r["file_path"]).exists()
        assert not (mem_dir / "habits" / "deleted").exists()

    def test_hard_delete_after_soft_delete(self, mem_dir):
        r = _add_one(mem_dir)
        delete_memory(r["file_path"], memory_dir=mem_dir)
        deleted_file = list((mem_dir / "habits" / "deleted").glob("*.md"))[0]
        result = delete_memory("habits/deleted/" + deleted_file.name, hard=True,
                               memory_dir=mem_dir)
        assert result["success"] is True
        assert not deleted_file.exists()


class TestDeleteGuards:
    def test_missing_file(self, mem_dir):
        result = delete_memory("habits/ghost.md", memory_dir=mem_dir)
        assert result["success"] is False

    def test_refuses_index_file(self, mem_dir):
        result = delete_memory("memory_index.md", memory_dir=mem_dir)
        assert result["success"] is False

    def test_refuses_path_traversal(self, mem_dir):
        result = delete_memory("../../outside.md", memory_dir=mem_dir)
        assert result["success"] is False
        assert "非法路径" in result["error"]

    def test_refuses_already_deleted(self, mem_dir):
        r = _add_one(mem_dir)
        delete_memory(r["file_path"], memory_dir=mem_dir)
        deleted_file = list((mem_dir / "habits" / "deleted").glob("*.md"))[0]
        result = delete_memory("habits/deleted/" + deleted_file.name, memory_dir=mem_dir)
        assert result["success"] is False
