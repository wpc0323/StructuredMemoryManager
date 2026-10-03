"""_base.py 单元测试：YAML 回退解析器、权重计算、路径防护、统计"""

import pytest

import _base
from _base import YAMLParser, compute_weight, resolve_within_memory_dir, get_memory_stats


# ============================================================
# YAML 回退解析器
# ============================================================

class TestFallbackParse:
    def test_flat_front_matter(self):
        text = (
            'entry_id: "2026-07-18-12-00-001"\n'
            'date: "2026-07-18T12:00:00+08:00"\n'
            'category: habit\n'
            'priority: high\n'
            'tags: [交互风格, emoji]\n'
            'summary: 用户明确要求永远不要使用emoji\n'
            'emphasis: true\n'
            'mention_count: 0\n'
            'expires: null\n'
        )
        fm = YAMLParser._fallback_parse(text)
        assert fm["entry_id"] == "2026-07-18-12-00-001"
        assert fm["category"] == "habit"
        assert fm["priority"] == "high"
        assert fm["tags"] == ["交互风格", "emoji"]
        assert fm["emphasis"] is True
        assert fm["mention_count"] == 0
        assert fm["expires"] is None

    def test_entries_list_of_dicts(self):
        text = (
            'last_modified: "2026-07-19T12:00:00+08:00"\n'
            'entries:\n'
            '  - path: "habits/no_emoji_001.md"\n'
            '    category: habit\n'
            '    summary: "决策: 使用PostgreSQL"\n'
            '    priority: high\n'
            '    tags: [交互风格, emoji]\n'
            '    entry_id: "2026-07-19-12-00-001"\n'
            '    emphasis: true\n'
            '  - path: "skills/react_003.md"\n'
            '    category: skill\n'
            '    summary: React Hooks性能优化模式\n'
            '    priority: medium\n'
            '    tags: []\n'
            '    entry_id: "2026-07-19-12-00-003"\n'
            '    emphasis: false\n'
            '    mention_count: 4\n'
        )
        fm = YAMLParser._fallback_parse(text)
        assert len(fm["entries"]) == 2
        e0, e1 = fm["entries"]
        assert e0["path"] == "habits/no_emoji_001.md"
        assert e0["summary"] == "决策: 使用PostgreSQL"  # 含冒号的值应被正确去引号
        assert e0["tags"] == ["交互风格", "emoji"]
        assert e0["emphasis"] is True
        assert e1["mention_count"] == 4
        assert e1["tags"] == []

    def test_block_scalar_list(self):
        # PyYAML dump 出的块风格标量列表，也要能被回退解析器读回
        text = (
            'category: habit\n'
            'tags:\n'
            '- 交互风格\n'
            '- emoji\n'
            'priority: high\n'
        )
        fm = YAMLParser._fallback_parse(text)
        assert fm["tags"] == ["交互风格", "emoji"]
        assert fm["priority"] == "high"

    def test_decision_log_block_list(self):
        text = (
            'category: project\n'
            'decision_log:\n'
            '- date: "2026-07-19T12:00:00+08:00"\n'
            '  decision: 选择React作为前端框架\n'
            '  entry_id: "2026-07-19-12-00-001"\n'
            'emphasis: false\n'
        )
        fm = YAMLParser._fallback_parse(text)
        assert fm["decision_log"] == [
            {
                "date": "2026-07-19T12:00:00+08:00",
                "decision": "选择React作为前端框架",
                "entry_id": "2026-07-19-12-00-001",
            }
        ]
        assert fm["emphasis"] is False


class TestFallbackDumpRoundtrip:
    SAMPLE = {
        "last_modified": "2026-07-19T12:00:00+08:00",
        "entries": [
            {
                "path": "habits/no_emoji_001.md",
                "category": "habit",
                "summary": "用户明确要求: 永远不要使用emoji",
                "priority": "high",
                "tags": ["交互风格", "emoji"],
                "entry_id": "2026-07-19-12-00-001",
                "last_modified": "2026-07-19T12:00:00+08:00",
                "emphasis": True,
            },
            {
                "path": "skills/react_003.md",
                "category": "skill",
                "summary": "React Hooks性能优化模式",
                "priority": "medium",
                "tags": [],
                "entry_id": "2026-07-19-12-00-003",
                "last_modified": "2026-07-19T12:00:00+08:00",
                "emphasis": False,
                "mention_count": 4,
            },
        ],
    }

    def test_fallback_dump_parse_roundtrip(self, monkeypatch):
        """无 PyYAML 时：dump 出的文本必须能被回退解析器完整读回"""
        monkeypatch.setattr(_base, "HAS_YAML", False)
        text = YAMLParser.dump(self.SAMPLE)
        parsed = YAMLParser.load(text)
        assert parsed == self.SAMPLE

    def test_fallback_dump_is_valid_yaml(self):
        """有 PyYAML 时：回退 dump 的输出必须是合法 YAML（保证跨环境兼容）"""
        yaml = pytest.importorskip("yaml")
        text = YAMLParser._fallback_dump(self.SAMPLE)
        parsed = yaml.safe_load(text)
        assert parsed == self.SAMPLE

    def test_pyyaml_dump_readable_by_fallback(self):
        """PyYAML dump 的块风格输出，回退解析器也应能读回"""
        yaml = pytest.importorskip("yaml")
        text = yaml.dump(self.SAMPLE, allow_unicode=True, default_flow_style=False, sort_keys=False)
        parsed = YAMLParser._fallback_parse(text)
        assert parsed == self.SAMPLE

    def test_front_matter_roundtrip_without_yaml(self, monkeypatch):
        """extract_front_matter 在无 PyYAML 环境下必须能解析出完整字段（回归修复验证）"""
        monkeypatch.setattr(_base, "HAS_YAML", False)
        content = (
            "---\n"
            "entry_id: \"2026-07-18-12-00-001\"\n"
            "category: habit\n"
            "priority: high\n"
            "tags: [交互风格]\n"
            "summary: 测试条目\n"
            "expires: null\n"
            "emphasis: true\n"
            "---\n"
            "\n"
            "正文内容\n"
        )
        fm, body = _base.extract_front_matter(content)
        assert fm["entry_id"] == "2026-07-18-12-00-001"
        assert fm["priority"] == "high"
        assert fm["emphasis"] is True
        assert body.strip() == "正文内容"


# ============================================================
# 权重计算
# ============================================================

class TestComputeWeight:
    def test_category_base_order(self):
        p = compute_weight("project", "medium", date_str="2026-01-01")
        h = compute_weight("habit", "medium", date_str="2026-01-01")
        s = compute_weight("skill", "medium", date_str="2026-01-01")
        assert p > h > s

    def test_habit_emphasis_beats_recency(self):
        emphasized = compute_weight("habit", "low", emphasis=True, date_str="2020-01-01")
        recent = compute_weight("habit", "low", emphasis=False, date_str=_base.now_iso())
        assert emphasized > recent

    def test_skill_mention_count_threshold(self):
        mentioned = compute_weight("skill", "low", mention_count=3, date_str="2020-01-01")
        plain = compute_weight("skill", "high", mention_count=0, date_str="2020-01-01")
        # 反复提及的 skill 应排在普通 high 之前（10+30 > 10+20）
        assert mentioned > plain

    def test_expired_penalty(self):
        expired = compute_weight("habit", "medium", date_str="2020-01-01", expires_str="2020-06-01")
        not_expired = compute_weight("habit", "medium", date_str="2020-01-01")
        assert expired == not_expired - 5

    def test_keyword_score(self):
        scored = compute_weight("habit", "medium", date_str="2020-01-01", keyword_score=7)
        assert scored == compute_weight("habit", "medium", date_str="2020-01-01") + 7


# ============================================================
# 路径防护
# ============================================================

class TestResolveWithinMemoryDir:
    def test_normal_relative_path(self, tmp_path):
        result = resolve_within_memory_dir("habits/a.md", tmp_path)
        assert result == (tmp_path / "habits" / "a.md").resolve()

    def test_traversal_rejected(self, tmp_path):
        assert resolve_within_memory_dir("../../outside.md", tmp_path) is None

    def test_absolute_path_rejected(self, tmp_path):
        assert resolve_within_memory_dir(str(tmp_path.parent / "evil.md"), tmp_path) is None

    def test_nested_normal_path(self, tmp_path):
        result = resolve_within_memory_dir("habits/archive/a.md", tmp_path)
        assert result is not None


# ============================================================
# 统计
# ============================================================

class TestMemoryStats:
    def test_stats_structure(self, tmp_path):
        stats = get_memory_stats(memory_dir=tmp_path / "memory")
        assert set(stats["categories"].keys()) == {"habit", "skill", "project"}
        assert stats["index_entries"] == 0
        assert isinstance(stats["pyyaml"], bool)
        assert isinstance(stats["chromadb"], bool)

    def test_stats_counts_files(self, tmp_path):
        mem_dir = tmp_path / "memory"
        _base.ensure_memory_dir(mem_dir)
        for i in range(3):
            _base.write_memory_file(
                mem_dir / "habits" / f"t{i}.md",
                {"entry_id": f"2026-01-01-00-00-{i:03d}", "category": "habit",
                 "priority": "low", "summary": f"条目{i}", "tags": []},
                "正文",
            )
        stats = get_memory_stats(memory_dir=mem_dir)
        assert stats["categories"]["habit"]["active_files"] == 3


# ============================================================
# 向量距离映射
# ============================================================

class TestDistanceMapping:
    def test_cosine_distance_mapping(self):
        from vector_store import _distance_to_similarity
        assert _distance_to_similarity(0.0) == 1.0
        assert _distance_to_similarity(0.25) == 0.75
        assert _distance_to_similarity(1.0) == 0.0
        # 超界钳制：远处结果趋近 0，而不是旧的 1/(1+d) 保底 1/3
        assert _distance_to_similarity(1.5) == 0.0
        assert _distance_to_similarity(-0.5) == 1.0
        assert _distance_to_similarity("bad") == 0.0
