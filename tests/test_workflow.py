"""端到端工作流测试：add → search → confirm → rebuild → 归档"""

import pytest

import _base
import add_memory as add_mod
import search_memory as search_mod
import confirm_memory as confirm_mod
import rebuild_index as rebuild_mod
from _base import read_memory_file, write_memory_file


@pytest.fixture(autouse=True)
def force_keyword_mode(monkeypatch):
    """强制关键字检索模式，保证测试确定性（不依赖 chromadb / 嵌入模型）"""
    monkeypatch.setattr(_base, "HAS_CHROMADB", False)


@pytest.fixture
def mem_dir(tmp_path):
    d = tmp_path / "memory"
    _base.ensure_memory_dir(d)
    return d


def add(mem_dir, **kwargs):
    return add_mod.add_memory(memory_dir=mem_dir, **kwargs)


def search(mem_dir, query, **kwargs):
    return search_mod.search_memory(query, memory_dir=mem_dir, use_vector=False, **kwargs)


def norm(path_str):
    """统一路径分隔符，保证断言在 Windows / POSIX 下都成立"""
    return path_str.replace("\\", "/")


# ============================================================
# 添加与检索
# ============================================================

class TestAddAndSearch:
    def test_add_returns_paths(self, mem_dir):
        result = add(mem_dir, category="habit", content="用户偏好深色主题",
                     priority="high", tags=["UI风格"])
        assert result["success"] is True
        assert norm(result["file_path"]).startswith("habits/")
        # 文件确实落盘
        assert (mem_dir / result["file_path"]).exists()

    def test_search_finds_by_keyword(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题", tags=["UI风格"])
        results = search(mem_dir, "深色主题")
        assert len(results) == 1
        assert "深色主题" in results[0]["summary"]
        assert results[0]["category"] == "habit"

    def test_search_no_match_returns_empty(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题")
        assert search(mem_dir, "完全无关的查询词xyz") == []

    def test_search_tag_filter(self, mem_dir):
        add(mem_dir, category="habit", content="偏好深色主题A", tags=["UI"])
        add(mem_dir, category="skill", content="React性能优化模式B", tags=["React"])
        results = search(mem_dir, "", tag_filter=["React"])
        assert len(results) == 1
        assert "React" in results[0]["tags"]

    def test_search_category_filter(self, mem_dir):
        add(mem_dir, category="habit", content="深色主题偏好")
        add(mem_dir, category="skill", content="深色主题相关的CSS技巧")
        results = search(mem_dir, "深色", category_filter="skill")
        assert len(results) == 1
        assert results[0]["category"] == "skill"

    def test_search_high_priority_only(self, mem_dir):
        add(mem_dir, category="habit", content="必须用中文回复", priority="high")
        add(mem_dir, category="habit", content="中文命名规范参考", priority="low")
        results = search(mem_dir, "中文", high_priority_only=True)
        assert len(results) == 1
        assert results[0]["priority"] == "high"

    def test_empty_query_lists_all(self, mem_dir):
        add(mem_dir, category="habit", content="偏好一")
        add(mem_dir, category="skill", content="技能二")
        results = search(mem_dir, "")
        assert len(results) == 2

    def test_weight_order_emphasis_first(self, mem_dir):
        add(mem_dir, category="habit", content="必须用中文回复所有对话",
            priority="high", emphasis=True)
        add(mem_dir, category="habit", content="对话中偶尔可用英文单词", priority="medium")
        results = search(mem_dir, "")
        assert len(results) == 2
        assert "中文回复" in results[0]["summary"]

    def test_weight_order_category(self, mem_dir):
        # 相同查询下 project > habit > skill
        add(mem_dir, category="skill", content="React框架优化方案", priority="low")
        add(mem_dir, category="habit", content="React风格的命名偏好", priority="low")
        add(mem_dir, category="project", content="React项目重构计划", priority="low",
            project_name="demo")
        results = search(mem_dir, "React")
        assert [r["category"] for r in results] == ["project", "habit", "skill"]

    def test_duplicate_content_creates_unique_files(self, mem_dir):
        r1 = add(mem_dir, category="habit", content="同样的内容")
        r2 = add(mem_dir, category="habit", content="同样的内容")
        assert r1["file_path"] != r2["file_path"]
        assert r1["entry_id"] != r2["entry_id"]


# ============================================================
# 项目记忆
# ============================================================

class TestProjectMemory:
    def test_project_append(self, mem_dir):
        add(mem_dir, category="project", content="选择PostgreSQL作为主数据库",
            priority="high", project_name="demo")
        r2 = add(mem_dir, category="project", content="改用MySQL作为主数据库",
                 priority="high", project_name="demo")
        # 同一项目文件追加
        assert norm(r2["file_path"]) == "projects/demo.md"
        fm, body = read_memory_file(mem_dir / "projects" / "demo.md")
        assert len(fm["decision_log"]) == 2
        # 最新的决策排在最前
        assert "MySQL" in fm["decision_log"][0]["decision"]
        # 索引中两条决策都可见
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        demo_entries = [e for e in index_fm["entries"]
                        if norm(e["path"]) == "projects/demo.md"]
        assert len(demo_entries) == 2

    def test_project_requires_name(self, mem_dir):
        with pytest.raises(ValueError):
            add(mem_dir, category="project", content="没有项目名")


# ============================================================
# confirm 操作
# ============================================================

class TestConfirm:
    def _add_skill(self, mem_dir):
        return add(mem_dir, category="skill", content="React Hooks优化模式",
                   priority="medium", tags=["React"])

    def test_emphasize_and_de_emphasize(self, mem_dir):
        r = self._add_skill(mem_dir)
        res = confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "emphasize",
                                         memory_dir=mem_dir)
        assert res["success"] is True
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["emphasis"] is True
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert index_fm["entries"][0]["emphasis"] is True

        confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "de_emphasize",
                                   memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["emphasis"] is False

    def test_upgrade_downgrade(self, mem_dir):
        r = self._add_skill(mem_dir)
        confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "upgrade",
                                   memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["priority"] == "high"
        confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "downgrade",
                                   memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["priority"] == "low"

    def test_confirm_clears_expires(self, mem_dir):
        r = add(mem_dir, category="habit", content="临时约定", priority="low",
                expires="2020-01-01")
        assert _base.is_expired("2020-01-01") is True
        confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "confirm",
                                   memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["expires"] is None

    def test_bump_mention(self, mem_dir):
        r = self._add_skill(mem_dir)
        confirm_mod.confirm_memory(r["file_path"], r["entry_id"], "bump_mention",
                                   memory_dir=mem_dir)
        fm, _ = read_memory_file(mem_dir / r["file_path"])
        assert fm["mention_count"] == 1

    def test_wrong_entry_id_rejected(self, mem_dir):
        r = self._add_skill(mem_dir)
        res = confirm_mod.confirm_memory(r["file_path"], "2099-01-01-00-00-999",
                                         "emphasize", memory_dir=mem_dir)
        assert res["success"] is False

    def test_missing_file_rejected(self, mem_dir):
        res = confirm_mod.confirm_memory("habits/ghost.md", "2026-01-01-00-00-001",
                                         "emphasize", memory_dir=mem_dir)
        assert res["success"] is False


# ============================================================
# read 与路径防护
# ============================================================

class TestRead:
    def test_read_full_content(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题", tags=["UI"])
        results = search(mem_dir, "深色")
        r = search_mod.read_memory(results[0]["file_path"], memory_dir=mem_dir)
        assert r["success"] is True
        assert "深色主题" in r["content"]

    def test_read_missing_file(self, mem_dir):
        r = search_mod.read_memory("habits/ghost.md", memory_dir=mem_dir)
        assert r["success"] is False

    def test_read_path_traversal_blocked(self, mem_dir):
        r = search_mod.read_memory("../../outside.md", memory_dir=mem_dir)
        assert r["success"] is False
        assert "非法路径" in r["error"]


# ============================================================
# rebuild
# ============================================================

class TestRebuild:
    def test_rebuild_restores_index(self, mem_dir):
        add(mem_dir, category="habit", content="偏好一")
        add(mem_dir, category="skill", content="技能二")
        # 删除索引模拟损坏
        (mem_dir / "memory_index.md").unlink()
        result = rebuild_mod.rebuild_index(memory_dir=mem_dir)
        assert result["success"] is True
        assert result["entries_count"] == 2
        # 重建后检索恢复
        assert len(search(mem_dir, "技能二")) == 1

    def test_rebuild_includes_archived(self, mem_dir):
        add(mem_dir, category="habit", content="要归档的旧记忆", priority="low")
        _base.ensure_memory_dir(mem_dir)
        (mem_dir / "habits" / "archive").mkdir(exist_ok=True)
        import shutil
        src = list((mem_dir / "habits").glob("*.md"))[0]
        shutil.move(str(src), str(mem_dir / "habits" / "archive" / src.name))
        rebuild_mod.rebuild_index(memory_dir=mem_dir)
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        entry_path = index_fm["entries"][0]["path"].replace("\\", "/")
        assert "archive/" in entry_path


# ============================================================
# 归档
# ============================================================

class TestArchiving:
    def test_archive_low_old_entries(self, mem_dir):
        # 直接写入 51 个低优且过旧的 habit 文件，超过阈值(50)
        for i in range(51):
            fm = {
                "entry_id": f"2020-01-01-00-00-{i:03d}",
                "date": "2020-01-01T00:00:00+08:00",
                "category": "habit",
                "priority": "low",
                "tags": [],
                "summary": f"归档测试旧条目{i}",
                "expires": None,
                "related_files": [],
                "last_modified": "2020-01-01T00:00:00+08:00",
                "emphasis": False,
            }
            write_memory_file(mem_dir / "habits" / f"old_entry_{i:03d}.md", fm, f"正文{i}")
        rebuild_mod.rebuild_index(memory_dir=mem_dir)

        # 再添加一条新记忆，触发归档检查（文件数 52 > 50）
        result = add(mem_dir, category="habit", content="触发归档的新记忆", priority="high")
        assert result["success"] is True
        assert "archive_notice" in result

        archived = list((mem_dir / "habits" / "archive").glob("*.md"))
        assert len(archived) == 51
        # 新记忆仍在活跃目录
        assert (mem_dir / result["file_path"]).exists()
        # 索引路径已同步指向 archive/
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        archived_paths = [e["path"] for e in index_fm["entries"] if "archive" in e["path"]]
        assert len(archived_paths) == 51

    def test_high_priority_never_archived(self, mem_dir):
        for i in range(51):
            fm = {
                "entry_id": f"2020-01-02-00-00-{i:03d}",
                "date": "2020-01-02T00:00:00+08:00",
                "category": "skill",
                "priority": "high" if i < 10 else "low",
                "tags": [],
                "summary": f"条目{i}",
                "expires": None,
                "related_files": [],
                "last_modified": "2020-01-02T00:00:00+08:00",
                "emphasis": False,
            }
            write_memory_file(mem_dir / "skills" / f"entry_{i:03d}.md", fm, f"正文{i}")
        result = add(mem_dir, category="skill", content="触发归档", priority="medium")
        archived = list((mem_dir / "skills" / "archive").glob("*.md"))
        assert len(archived) == 41  # 只有 low 被归档，10 个 high 保留


# ============================================================
# stats
# ============================================================

class TestStats:
    def test_stats_reflects_state(self, mem_dir):
        add(mem_dir, category="habit", content="偏好一")
        add(mem_dir, category="skill", content="技能二")
        stats = _base.get_memory_stats(memory_dir=mem_dir)
        assert stats["categories"]["habit"]["active_files"] == 1
        assert stats["categories"]["skill"]["active_files"] == 1
        assert stats["index_entries"] == 2


# ============================================================
# 无 PyYAML 回退模式端到端（走真实读写闭环，而非仅解析器单元测试）
# ============================================================

class TestNoPyYAMLEndToEnd:
    def test_add_search_roundtrip_without_pyyaml(self, mem_dir, monkeypatch):
        monkeypatch.setattr(_base, "HAS_YAML", False)
        add(mem_dir, category="habit", content="用户偏好深色主题",
            priority="high", tags=["UI"])
        add(mem_dir, category="project", content="选择PostgreSQL作为主数据库",
            priority="high", project_name="demo")

        results = search(mem_dir, "深色")
        assert len(results) == 1
        # 连续写入不得覆盖或重复索引块
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert len(index_fm["entries"]) == 2
        assert index_fm["entries"][0]["last_modified"] != ""

    def test_read_memory_file_roundtrip_without_pyyaml(self, mem_dir, monkeypatch):
        monkeypatch.setattr(_base, "HAS_YAML", False)
        r = add(mem_dir, category="skill", content="React Hooks优化模式",
                priority="medium", tags=["React"])
        fm, body = read_memory_file(mem_dir / r["file_path"])
        assert fm["entry_id"] == r["entry_id"]
        assert fm["priority"] == "medium"
        assert "React Hooks优化模式" in body

    def test_extract_front_matter_tolerates_glued_delimiter(self, monkeypatch):
        """历史遗留格式：闭合 --- 与末行粘连时仍能解析"""
        monkeypatch.setattr(_base, "HAS_YAML", False)
        content = "---\nentry_id: \"001\"\ncategory: habit---\n\n正文内容\n"
        fm, body = _base.extract_front_matter(content)
        assert fm.get("entry_id") == "001"
        assert fm.get("category") == "habit"
        assert "正文内容" in body

    def test_extract_front_matter_handles_crlf(self):
        """Windows CRLF 文件必须能正常解析"""
        content = "---\r\nentry_id: \"001\"\r\npriority: high\r\ntags: [a, b]\r\n---\r\n\r\n正文\r\n"
        fm, body = _base.extract_front_matter(content)
        assert fm.get("entry_id") == "001"
        assert fm.get("priority") == "high"
        assert fm.get("tags") == ["a", "b"]
