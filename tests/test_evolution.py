"""v3.3 记忆演化特性测试：时间衰减、检索热度、supersede、自动互链、关联扩展"""

from datetime import timedelta

import pytest

import _base
import add_memory as add_mod
import search_memory as search_mod
import confirm_memory as confirm_mod
from _base import read_memory_file, recency_factor, compute_weight


def iso_days_ago(days: int) -> str:
    """返回 N 天前的 ISO 8601 时间字符串（本地时区）"""
    dt = _base.datetime.now(_base.TIMEZONE_CN) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


@pytest.fixture(autouse=True)
def force_keyword_mode(monkeypatch):
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


# ============================================================
# 时间衰减
# ============================================================

class TestRecencyDecay:
    def test_decay_values(self):
        now = _base.now_iso()
        assert recency_factor(now) == 1.0
        # 半衰期 30 天：30 天前约 0.5，90 天前约 0.125
        assert abs(recency_factor(iso_days_ago(30)) - 0.5) < 0.01
        assert abs(recency_factor(iso_days_ago(90)) - 0.125) < 0.01
        # 一年后趋近 0
        assert recency_factor(iso_days_ago(365)) < 0.01
        assert recency_factor(None) == 0.0

    def test_continuous_not_binary(self):
        """衰减是连续的：30 天和 40 天的记忆有明显差异（旧版二者同为满/零）"""
        d30 = compute_weight("habit", "low", date_str=iso_days_ago(30))
        d40 = compute_weight("habit", "low", date_str=iso_days_ago(40))
        assert d30 > d40

    def test_very_old_memory_still_rankable(self):
        """一年前的记忆 recency 趋近 0，但分类/优先级/匹配分仍然有效"""
        old = compute_weight("habit", "high", date_str=iso_days_ago(365), keyword_score=3)
        assert abs(old - (20 + 0 + 20 + 3)) < 0.1  # recency 衰减趋近 0


# ============================================================
# 检索热度反馈回路
# ============================================================

class TestAccessTracking:
    def test_search_increments_access_count(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题", tags=["UI"])
        r1 = search(mem_dir, "深色主题")
        assert len(r1) == 1
        fm, _ = read_memory_file(mem_dir / r1[0]["file_path"])
        assert fm["access_count"] == 1
        assert fm.get("last_accessed")

        search(mem_dir, "深色主题")
        fm, _ = read_memory_file(mem_dir / r1[0]["file_path"])
        assert fm["access_count"] == 2

    def test_access_count_synced_to_index(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题", tags=["UI"])
        search(mem_dir, "深色主题")
        index_fm = _base.read_memory_index(memory_dir=mem_dir)
        assert index_fm["entries"][0]["access_count"] == 1

    def test_access_bonus_affects_ranking(self, mem_dir):
        """两条内容相近的记忆，被检索过多次的热门记忆排名靠前"""
        add(mem_dir, category="skill", content="React useMemo 缓存技巧", tags=["React", "性能优化"], priority="medium")
        add(mem_dir, category="skill", content="React useCallback 缓存技巧", tags=["React", "性能优化"], priority="medium", allow_dedup=False)
        # 反复检索第一条相关的内容
        for _ in range(4):
            search(mem_dir, "useMemo")
        results = search(mem_dir, "缓存技巧")
        assert len(results) == 2
        assert "useMemo" in results[0]["summary"]

    def test_track_access_disabled(self, mem_dir):
        add(mem_dir, category="habit", content="用户偏好深色主题", tags=["UI"])
        search(mem_dir, "深色主题", track_access=False)
        results = search(mem_dir, "深色主题", track_access=False)
        fm, _ = read_memory_file(mem_dir / results[0]["file_path"])
        assert fm.get("access_count", 0) == 0

    def test_access_bonus_capped(self):
        assert compute_weight("habit", "low", access_count=100) - \
               compute_weight("habit", "low") == _base.ACCESS_BONUS_MAX


# ============================================================
# supersede 冲突失效
# ============================================================

class TestSupersede:
    def test_supersede_marks_and_demotes(self, mem_dir):
        r_old = add(mem_dir, category="habit", content="缩进统一使用Tab",
                    priority="high", tags=["代码风格"])
        r_new = add(mem_dir, category="habit", content="缩进统一使用4个空格",
                    priority="high", tags=["代码风格"], allow_dedup=False)

        result = confirm_mod.confirm_memory(
            r_old["file_path"], r_old["entry_id"], "supersede",
            superseded_by=r_new["file_path"], memory_dir=mem_dir)
        assert result["success"] is True

        fm, _ = read_memory_file(mem_dir / r_old["file_path"])
        assert fm["superseded_by"] == r_new["file_path"].replace("\\", "/")
        assert fm["priority"] == "low"

    def test_superseded_excluded_from_search(self, mem_dir):
        r_old = add(mem_dir, category="habit", content="缩进统一使用Tab",
                    priority="high", tags=["代码风格"])
        r_new = add(mem_dir, category="habit", content="缩进统一使用4个空格",
                    priority="high", tags=["代码风格"], allow_dedup=False)
        confirm_mod.confirm_memory(r_old["file_path"], r_old["entry_id"], "supersede",
                                   superseded_by=r_new["file_path"], memory_dir=mem_dir)
        results = search(mem_dir, "缩进")
        assert len(results) == 1
        assert "空格" in results[0]["summary"]

    def test_superseded_still_readable(self, mem_dir):
        r_old = add(mem_dir, category="habit", content="缩进统一使用Tab", priority="high")
        r_new = add(mem_dir, category="habit", content="缩进统一使用4个空格", priority="high",
                    allow_dedup=False)
        confirm_mod.confirm_memory(r_old["file_path"], r_old["entry_id"], "supersede",
                                   superseded_by=r_new["file_path"], memory_dir=mem_dir)
        r = search_mod.read_memory(r_old["file_path"], memory_dir=mem_dir)
        assert r["success"] is True  # 历史保留，read 仍可查

    def test_supersede_requires_target(self, mem_dir):
        r_old = add(mem_dir, category="habit", content="缩进统一使用Tab", priority="high")
        result = confirm_mod.confirm_memory(r_old["file_path"], r_old["entry_id"],
                                            "supersede", memory_dir=mem_dir)
        assert result["success"] is False

    def test_rebuild_keeps_superseded_marker(self, mem_dir):
        r_old = add(mem_dir, category="habit", content="缩进统一使用Tab", priority="high")
        r_new = add(mem_dir, category="habit", content="缩进统一使用4个空格", priority="high",
                    allow_dedup=False)
        confirm_mod.confirm_memory(r_old["file_path"], r_old["entry_id"], "supersede",
                                   superseded_by=r_new["file_path"], memory_dir=mem_dir)
        from rebuild_index import rebuild_index
        rebuild_index(memory_dir=mem_dir)
        results = search(mem_dir, "缩进")
        assert len(results) == 1
        assert "空格" in results[0]["summary"]


# ============================================================
# 标签自动互链 + 关联扩展
# ============================================================

class TestAutoLinkAndExpansion:
    def test_two_shared_tags_create_bidirectional_links(self, mem_dir):
        r1 = add(mem_dir, category="skill", content="React useMemo 缓存计算结果",
                 tags=["React", "性能优化"])
        r2 = add(mem_dir, category="skill", content="React useCallback 稳定回调",
                 tags=["React", "性能优化"], allow_dedup=False)
        fm1, _ = read_memory_file(mem_dir / r1["file_path"])
        fm2, _ = read_memory_file(mem_dir / r2["file_path"])
        assert any(p.endswith(r2["file_path"].split("/")[-1]) or p.replace("\\", "/") == r2["file_path"].replace("\\", "/")
                   for p in fm1["related_files"])
        assert any(p.replace("\\", "/") == r1["file_path"].replace("\\", "/")
                   for p in fm2["related_files"])

    def test_fewer_shared_tags_no_link(self, mem_dir):
        add(mem_dir, category="skill", content="React 组件模式", tags=["React", "组件"])
        r2 = add(mem_dir, category="skill", content="Vue 响应式原理", tags=["Vue", "组件"],
                 allow_dedup=False)
        fm, _ = read_memory_file(mem_dir / r2["file_path"])
        assert fm["related_files"] == []

    def test_search_expands_related(self, mem_dir):
        add(mem_dir, category="skill", content="React useMemo 缓存计算结果",
            tags=["React", "性能优化"])
        r2 = add(mem_dir, category="skill", content="React useCallback 稳定回调",
                 tags=["React", "性能优化"], allow_dedup=False)
        results = search(mem_dir, "useCallback")
        assert len(results) == 1
        related = results[0].get("related", [])
        assert len(related) >= 1
        assert any("useMemo" in rel["summary"] for rel in related)

    def test_expansion_disabled(self, mem_dir):
        add(mem_dir, category="skill", content="React useMemo 缓存计算结果",
            tags=["React", "性能优化"])
        add(mem_dir, category="skill", content="React useCallback 稳定回调",
            tags=["React", "性能优化"], allow_dedup=False)
        results = search(mem_dir, "useCallback", expand_related=False)
        assert "related" not in results[0]

    def test_link_cap(self, mem_dir):
        """自动互链不超过 AUTO_LINK_MAX_LINKS 条"""
        for i in range(8):
            add(mem_dir, category="skill", content=f"React 优化技巧第{i}条",
                tags=["React", "性能优化"], allow_dedup=False)
        # 第 9 条（首条被后续互链，这里检查最后一条的关联数 <= 上限）
        r_last = add(mem_dir, category="skill", content="React 优化技巧收尾",
                     tags=["React", "性能优化"], allow_dedup=False)
        fm, _ = read_memory_file(mem_dir / r_last["file_path"])
        auto_links = [p for p in fm["related_files"]]
        assert len(auto_links) <= _base.AUTO_LINK_MAX_LINKS
