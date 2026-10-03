"""自动去重测试：重复内容合并、优先级/强调/提及升级、--no-dedup 强制新建"""

import pytest

import _base
import add_memory as add_mod
import delete_memory as delete_mod
from _base import read_memory_file


@pytest.fixture(autouse=True)
def force_keyword_mode(monkeypatch):
    monkeypatch.setattr(_base, "HAS_CHROMADB", False)


@pytest.fixture
def mem_dir(tmp_path):
    d = tmp_path / "memory"
    _base.ensure_memory_dir(d)
    return d


class TestKeywordDedup:
    def test_exact_duplicate_merges(self, mem_dir):
        r1 = add_mod.add_memory(category="habit", content="用户偏好深色主题",
                                priority="medium", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="habit", content="用户偏好深色主题",
                                priority="medium", memory_dir=mem_dir)
        assert r2["deduplicated"] is True
        assert r2["merged_into"]["entry_id"] == r1["entry_id"]
        assert r2["merged_into"]["file_path"] == r1["file_path"]
        # 只有一个文件，且逐字重复的内容不会重复追加
        files = list((mem_dir / "habits").glob("*.md"))
        assert len(files) == 1
        _, body = read_memory_file(files[0])
        assert body.count("用户偏好深色主题") == 1

    def test_new_content_appended_losslessly(self, mem_dir):
        add_mod.add_memory(category="skill", content="React Hooks优化：useMemo缓存计算",
                           memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="skill", content="用户偏好深色主题",
                                allow_dedup=False, memory_dir=mem_dir)
        # 不相关内容正常新建
        assert r2.get("deduplicated") is None

    def test_skill_merge_bumps_mention_count(self, mem_dir):
        r1 = add_mod.add_memory(category="skill", content="React Hooks性能优化模式",
                                mention_count=2, memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="skill", content="React Hooks性能优化模式",
                                memory_dir=mem_dir)
        assert r2["deduplicated"] is True
        fm, _ = read_memory_file(mem_dir / r1["file_path"])
        assert fm["mention_count"] == 3

    def test_merge_propagates_emphasis(self, mem_dir):
        r1 = add_mod.add_memory(category="habit", content="必须用中文回复",
                                memory_dir=mem_dir)
        add_mod.add_memory(category="habit", content="必须用中文回复",
                           emphasis=True, memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r1["file_path"])
        assert fm["emphasis"] is True
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert index_fm["entries"][0]["emphasis"] is True

    def test_merge_upgrades_priority_never_downgrades(self, mem_dir):
        r1 = add_mod.add_memory(category="habit", content="必须用中文回复",
                                priority="medium", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="habit", content="必须用中文回复",
                                priority="high", memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r1["file_path"])
        assert fm["priority"] == "high"
        # 低优先级的新内容不会把已有 high 拉低
        r3 = add_mod.add_memory(category="habit", content="必须用中文回复",
                                priority="low", memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r1["file_path"])
        assert fm["priority"] == "high"

    def test_distinct_content_not_merged(self, mem_dir):
        add_mod.add_memory(category="habit", content="用户偏好深色主题", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="habit", content="用户喜欢简洁的代码风格",
                                memory_dir=mem_dir)
        assert r2.get("deduplicated") is None
        assert len(list((mem_dir / "habits").glob("*.md"))) == 2

    def test_dedup_respects_category(self, mem_dir):
        add_mod.add_memory(category="habit", content="用户偏好深色主题", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="skill", content="用户偏好深色主题",
                                memory_dir=mem_dir)
        # 同文不同类不算重复
        assert r2.get("deduplicated") is None

    def test_project_not_deduplicated(self, mem_dir):
        r1 = add_mod.add_memory(category="project", content="选择PostgreSQL作为主数据库",
                                priority="high", project_name="demo", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="project", content="选择PostgreSQL作为主数据库",
                                priority="high", project_name="demo", memory_dir=mem_dir)
        # project 走单文件追加逻辑，不做去重合并
        assert r2.get("deduplicated") is None
        assert r2["entry_id"] != r1["entry_id"]

    def test_no_dedup_flag(self, mem_dir):
        add_mod.add_memory(category="habit", content="用户偏好深色主题", memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="habit", content="用户偏好深色主题",
                                allow_dedup=False, memory_dir=mem_dir)
        assert r2.get("deduplicated") is None
        assert len(list((mem_dir / "habits").glob("*.md"))) == 2

    def test_deleted_memory_not_used_as_merge_target(self, mem_dir):
        """已软删除的记忆不应成为合并目标，重复内容应新建文件"""
        r1 = add_mod.add_memory(category="habit", content="用户偏好深色主题",
                                memory_dir=mem_dir)
        delete_mod.delete_memory(r1["file_path"], memory_dir=mem_dir)
        r2 = add_mod.add_memory(category="habit", content="用户偏好深色主题",
                                memory_dir=mem_dir)
        assert r2.get("deduplicated") is None
        assert len(list((mem_dir / "habits").glob("*.md"))) == 1
