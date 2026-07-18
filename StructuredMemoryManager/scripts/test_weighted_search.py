#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - 加权检索功能测试
============================================
验证所有功能正常工作，特别是加权检索规范。
"""

import sys
import os
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 添加脚本目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from _base import (
    compute_weight, resolve_conflict, CATEGORY_WEIGHT,
    PROJECT_SUB_WEIGHTS, HABIT_SUB_WEIGHTS, SKILL_SUB_WEIGHTS,
    PRIORITY_WEIGHT_MAP, days_since, now_iso, YAMLParser,
    extract_front_matter, build_front_matter, ensure_memory_dir,
    get_entry_file_path, read_memory_file, write_memory_file,
    read_memory_index, write_memory_index, MEMORY_DIR,
)
from add_memory import add_memory, _generate_summary
from search_memory import search_memory, read_memory
from confirm_memory import confirm_memory
from rebuild_index import rebuild_index


# 使用临时目录进行测试
TEST_DIR = Path(tempfile.mkdtemp(prefix="memory_test_"))


def setup_test_env():
    """创建测试用的记忆目录结构"""
    # 创建子目录
    (TEST_DIR / "habits").mkdir(parents=True, exist_ok=True)
    (TEST_DIR / "skills").mkdir(parents=True, exist_ok=True)
    (TEST_DIR / "projects").mkdir(parents=True, exist_ok=True)

    # 创建空的 memory_index.md
    index_fm = {
        "last_modified": now_iso(),
        "entries": []
    }
    write_memory_file(TEST_DIR / "memory_index.md", index_fm,
                      "# 记忆总目录\n\n测试用\n")

    print(f"[SETUP] 测试目录: {TEST_DIR}")


def cleanup_test_env():
    """清理测试目录"""
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
        print(f"[CLEANUP] 已清理测试目录")


# ============================================================
# 测试用例
# ============================================================

def test_compute_weight():
    """测试权重计算逻辑"""
    print("\n=== 测试 compute_weight ===")

    now = now_iso()
    old_date = "2025-01-01T00:00:00+08:00"  # 很久以前

    # 测试1: project 分类基础权重最高
    w_project = compute_weight(category="project", priority="high", date_str=now)
    w_habit = compute_weight(category="habit", priority="high", date_str=now)
    w_skill = compute_weight(category="skill", priority="high", date_str=now)
    assert w_project > w_habit > w_skill, \
        f"project({w_project}) > habit({w_habit}) > skill({w_skill}) 不成立"
    print(f"  [PASS] 分类基础权重: project({w_project}) > habit({w_habit}) > skill({w_skill})")

    # 测试2: project 中近期优先于强调
    w_recent = compute_weight(category="project", priority="medium", date_str=now)
    w_emphasis = compute_weight(category="project", priority="medium", emphasis=True, date_str=old_date)
    # 近期(project): recency(25) vs 强调: emphasis(15)
    assert w_recent > w_emphasis, \
        f"project近期({w_recent}) 应优先于强调({w_emphasis})"
    print(f"  [PASS] project: 近期({w_recent}) > 强调({w_emphasis})")

    # 测试3: habit 中强调优先于近期
    w_habit_emphasis = compute_weight(category="habit", priority="medium", emphasis=True, date_str=old_date)
    w_habit_recent = compute_weight(category="habit", priority="medium", date_str=now)
    # 强调(habit): emphasis(25) vs 近期: recency(15)
    assert w_habit_emphasis > w_habit_recent, \
        f"habit强调({w_habit_emphasis}) 应优先于近期({w_habit_recent})"
    print(f"  [PASS] habit: 强调({w_habit_emphasis}) > 近期({w_habit_recent})")

    # 测试4: skill 中 mention_count>=3 等同于 emphasis
    w_skill_mention = compute_weight(category="skill", priority="medium", mention_count=3)
    w_skill_emphasis = compute_weight(category="skill", priority="medium", emphasis=True)
    w_skill_normal = compute_weight(category="skill", priority="medium")
    assert w_skill_mention == w_skill_emphasis, \
        f"skill提及3次({w_skill_mention}) 应等于强调({w_skill_emphasis})"
    assert w_skill_mention > w_skill_normal, \
        f"skill强调({w_skill_mention}) 应优先于普通({w_skill_normal})"
    print(f"  [PASS] skill: 提及3次({w_skill_mention}) == 强调({w_skill_emphasis}) > 普通({w_skill_normal})")

    # 测试5: 优先级权重
    w_high = compute_weight(category="habit", priority="high", date_str=now)
    w_med = compute_weight(category="habit", priority="medium", date_str=now)
    w_low = compute_weight(category="habit", priority="low", date_str=now)
    assert w_high > w_med > w_low, \
        f"high({w_high}) > medium({w_med}) > low({w_low}) 不成立"
    print(f"  [PASS] 优先级权重: high({w_high}) > medium({w_med}) > low({w_low})")

    print("  === compute_weight 全部通过 ===")


def test_resolve_conflict():
    """测试冲突解决"""
    print("\n=== 测试 resolve_conflict ===")

    memories = [
        {"summary": "低权重", "weight": 10},
        {"summary": "高权重", "weight": 50},
        {"summary": "中权重", "weight": 30},
    ]

    resolved = resolve_conflict(memories)
    assert resolved[0]["weight"] == 50, "高权重应排第一"
    assert resolved[1]["weight"] == 30, "中权重应排第二"
    assert resolved[2]["weight"] == 10, "低权重应排第三"
    print(f"  [PASS] 冲突解决: 按权重降序排列")

    print("  === resolve_conflict 全部通过 ===")


def test_add_memory():
    """测试添加记忆功能"""
    print("\n=== 测试 add_memory ===")

    # 测试1: 添加 habit 类型记忆（带 emphasis）
    r1 = add_memory(
        category="habit",
        content="用户明确要求永远不要使用emoji",
        priority="high",
        tags=["交互风格", "emoji"],
        emphasis=True,
        memory_dir=TEST_DIR,
    )
    assert r1["success"], f"添加habit失败: {r1}"
    assert "entry_id" in r1
    print(f"  [PASS] 添加habit(强调): {r1['entry_id']}")

    # 测试2: 添加 skill 类型记忆（带 mention_count）
    r2 = add_memory(
        category="skill",
        content="React Hooks 性能优化模式：useMemo 缓存计算结果",
        priority="medium",
        tags=["React", "性能优化"],
        mention_count=4,
        memory_dir=TEST_DIR,
    )
    assert r2["success"], f"添加skill失败: {r2}"
    print(f"  [PASS] 添加skill(提及4次): {r2['entry_id']}")

    # 测试3: 添加 project 类型记忆
    r3 = add_memory(
        category="project",
        content="选择 PostgreSQL 作为主数据库，需要 JSONB 支持",
        priority="high",
        tags=["技术选型", "数据库"],
        project_name="data_platform",
        emphasis=True,
        memory_dir=TEST_DIR,
    )
    assert r3["success"], f"添加project失败: {r3}"
    print(f"  [PASS] 添加project(强调): {r3['entry_id']}")

    # 测试4: 添加普通 skill（无强调、无提及）
    r4 = add_memory(
        category="skill",
        content="Python 列表推导式的基本用法",
        priority="low",
        tags=["Python", "基础"],
        memory_dir=TEST_DIR,
    )
    assert r4["success"], f"添加skill(普通)失败: {r4}"
    print(f"  [PASS] 添加skill(普通): {r4['entry_id']}")

    # 测试5: 添加普通 habit（无强调）
    r5 = add_memory(
        category="habit",
        content="偏好暗色主题和简洁UI设计",
        priority="medium",
        tags=["UI风格"],
        memory_dir=TEST_DIR,
    )
    assert r5["success"], f"添加habit(普通)失败: {r5}"
    print(f"  [PASS] 添加habit(普通): {r5['entry_id']}")

    print("  === add_memory 全部通过 ===")


def test_search_memory_weighted():
    """测试加权检索排序"""
    print("\n=== 测试 search_memory 加权检索 ===")

    # 搜索所有记忆
    results = search_memory(query="", memory_dir=TEST_DIR)

    # Debug: check index
    from _base import read_memory_file as _rmf
    idx_path = TEST_DIR / "memory_index.md"
    if idx_path.exists():
        idx_fm, _ = _rmf(idx_path)
        idx_entries = idx_fm.get("entries", [])
        print(f"  [DEBUG] 索引中共有 {len(idx_entries)} 条记录")
        for e in idx_entries:
            print(f"    - {e.get('category', '?')} | {e.get('summary', '?')[:30]} | tags={e.get('tags', [])}")

    print(f"  检索到 {len(results)} 条记忆:")
    for i, r in enumerate(results):
        emp = " [强调]" if r.get("emphasis") else ""
        mc = f" [提及{r.get('mention_count',0)}次]" if r.get("mention_count", 0) > 0 else ""
        print(f"    [{i+1}] {r['category']} | priority={r['priority']}{emp}{mc} | weight={r['weight']} | {r['summary']}")

    # 验证加权排序规则
    if len(results) >= 2:
        # 确认结果按权重降序
        for i in range(len(results) - 1):
            assert results[i]["weight"] >= results[i+1]["weight"], \
                f"权重排序错误: {results[i]['weight']} < {results[i+1]['weight']}"
        print(f"  [PASS] 结果按权重降序排列")

    # 分类过滤测试
    project_results = search_memory(query="", category_filter="project", memory_dir=TEST_DIR)
    for r in project_results:
        assert r["category"] == "project", f"分类过滤错误: {r['category']}"
    print(f"  [PASS] 分类过滤: project 返回 {len(project_results)} 条")

    # 高优过滤测试
    high_results = search_memory(query="", high_priority_only=True, memory_dir=TEST_DIR)
    for r in high_results:
        assert r["priority"] == "high", f"高优过滤错误: priority={r['priority']}"
    print(f"  [PASS] 高优过滤: 返回 {len(high_results)} 条")

    # 关键词检索测试
    react_results = search_memory(query="React", memory_dir=TEST_DIR)
    assert len(react_results) > 0, "React 关键词检索应返回结果"
    print(f"  [PASS] 关键词检索: 'React' 返回 {len(react_results)} 条")

    print("  === search_memory 加权检索全部通过 ===")


def test_weight_priority_rules():
    """测试加权检索规范的具体权重排序规则"""
    print("\n=== 测试加权检索规范排序规则 ===")

    now = now_iso()
    old = "2025-01-01T00:00:00+08:00"

    # 规则1: project 中近期 > 强调
    w_project_recent = compute_weight("project", "high", date_str=now)
    w_project_emphasis_old = compute_weight("project", "high", emphasis=True, date_str=old)
    assert w_project_recent > w_project_emphasis_old, \
        f"project近期({w_project_recent}) 应 > project强调旧({w_project_emphasis_old})"
    print(f"  [PASS] 规则1 - project: 近期({w_project_recent}) > 强调旧({w_project_emphasis_old})")

    # 规则2: habit 中强调 > 近期
    w_habit_emphasis = compute_weight("habit", "high", emphasis=True, date_str=old)
    w_habit_recent = compute_weight("habit", "high", date_str=now)
    assert w_habit_emphasis > w_habit_recent, \
        f"habit强调({w_habit_emphasis}) 应 > habit近期({w_habit_recent})"
    print(f"  [PASS] 规则2 - habit: 强调({w_habit_emphasis}) > 近期({w_habit_recent})")

    # 规则3: skill 中强调/反复提及 > 其余
    w_skill_emphasis = compute_weight("skill", "medium", emphasis=True)
    w_skill_mention3 = compute_weight("skill", "medium", mention_count=3)
    w_skill_normal = compute_weight("skill", "medium")
    assert w_skill_emphasis > w_skill_normal, \
        f"skill强调({w_skill_emphasis}) 应 > skill普通({w_skill_normal})"
    assert w_skill_mention3 > w_skill_normal, \
        f"skill提及3次({w_skill_mention3}) 应 > skill普通({w_skill_normal})"
    print(f"  [PASS] 规则3 - skill: 强调({w_skill_emphasis}) = 提及3次({w_skill_mention3}) > 普通({w_skill_normal})")

    # 规则4: 分类间 project > habit > skill
    w_p = compute_weight("project", "medium", date_str=now)
    w_h = compute_weight("habit", "medium", date_str=now)
    w_s = compute_weight("skill", "medium", date_str=now)
    assert w_p > w_h > w_s, \
        f"project({w_p}) > habit({w_h}) > skill({w_s}) 不成立"
    print(f"  [PASS] 规则4 - 分类间: project({w_p}) > habit({w_h}) > skill({w_s})")

    # 规则5: 高权重不可被低权重覆盖
    memories = [
        {"summary": "旧偏好：用暗色主题", "weight": 20, "category": "habit"},
        {"summary": "新强调：必须用亮色主题", "weight": 65, "category": "habit", "emphasis": True},
    ]
    resolved = resolve_conflict(memories)
    assert resolved[0]["weight"] == 65, "冲突解决：高权重应排第一"
    print(f"  [PASS] 规则5 - 冲突解决：高权重优先")

    print("  === 加权检索规范排序规则全部通过 ===")


def test_confirm_memory():
    """测试确认/更新记忆功能"""
    print("\n=== 测试 confirm_memory ===")

    # 先添加一条记忆
    r = add_memory(
        category="skill",
        content="Python 数据处理管道模式",
        priority="medium",
        tags=["Python", "数据处理"],
        memory_dir=TEST_DIR,
    )
    assert r["success"]

    file_path = r["file_path"]
    entry_id = r["entry_id"]

    # 测试 upgrade
    r_upgrade = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="upgrade",
        memory_dir=TEST_DIR,
    )
    assert r_upgrade["success"], f"upgrade失败: {r_upgrade}"
    print(f"  [PASS] upgrade: {r_upgrade['message']}")

    # 测试 emphasize
    r_emph = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="emphasize",
        memory_dir=TEST_DIR,
    )
    assert r_emph["success"], f"emphasize失败: {r_emph}"
    print(f"  [PASS] emphasize: {r_emph['message']}")

    # 测试 bump_mention
    r_bump = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="bump_mention",
        mention_count=5,
        memory_dir=TEST_DIR,
    )
    assert r_bump["success"], f"bump_mention失败: {r_bump}"
    print(f"  [PASS] bump_mention: {r_bump['message']}")

    # 测试 de_emphasize
    r_de = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="de_emphasize",
        memory_dir=TEST_DIR,
    )
    assert r_de["success"], f"de_emphasize失败: {r_de}"
    print(f"  [PASS] de_emphasize: {r_de['message']}")

    # 验证读取的 emphasis 状态
    read_result = read_memory(file_path, memory_dir=TEST_DIR)
    assert read_result["success"]
    assert read_result["emphasis"] == False, f"de_emphasize后应为False: {read_result['emphasis']}"
    assert read_result["mention_count"] == 5, f"mention_count应为5: {read_result['mention_count']}"
    print(f"  [PASS] 读取验证: emphasis=False, mention_count=5")

    # 测试 confirm
    r_confirm = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="confirm",
        memory_dir=TEST_DIR,
    )
    assert r_confirm["success"], f"confirm失败: {r_confirm}"
    print(f"  [PASS] confirm: {r_confirm['message']}")

    # 测试 downgrade
    r_down = confirm_memory(
        file_path=file_path,
        entry_id=entry_id,
        action="downgrade",
        memory_dir=TEST_DIR,
    )
    assert r_down["success"], f"downgrade失败: {r_down}"
    print(f"  [PASS] downgrade: {r_down['message']}")

    print("  === confirm_memory 全部通过 ===")


def test_rebuild_index():
    """测试重建索引功能"""
    print("\n=== 测试 rebuild_index ===")

    result = rebuild_index(memory_dir=TEST_DIR)
    assert result["success"], f"rebuild_index失败: {result}"
    assert result["entries_count"] >= 0
    print(f"  [PASS] 重建索引完成: {result['message']}")

    # 验证索引中包含 emphasis 字段
    index_fm = read_memory_index()
    # 手动设置 memory_dir
    from _base import MEMORY_DIR as _MD
    # 需要用测试目录读取
    index_path = TEST_DIR / "memory_index.md"
    fm, body = read_memory_file(index_path)
    entries = fm.get("entries", [])
    for entry in entries:
        assert "emphasis" in entry, f"索引条目缺少emphasis字段: {entry}"
    print(f"  [PASS] 索引条目包含emphasis字段")

    # skill 类别索引条目检查 mention_count
    skill_entries = [e for e in entries if e.get("category") == "skill" and e.get("mention_count", 0) > 0]
    print(f"  [INFO] 含mention_count的skill条目: {len(skill_entries)}")

    print("  === rebuild_index 全部通过 ===")


def test_yaml_parser():
    """测试 YAML 解析器"""
    print("\n=== 测试 YAML 解析器 ===")

    # 测试基础解析
    yaml_text = """
name: test
priority: high
emphasis: true
tags: [Python, React]
"""
    result = YAMLParser.load(yaml_text)
    assert result.get("name") == "test"
    assert result.get("priority") == "high"
    assert result.get("emphasis") == True
    print(f"  [PASS] YAML基础解析: {result}")

    # 测试 dump
    dump_result = YAMLParser.dump({"emphasis": True, "mention_count": 5})
    assert "emphasis" in dump_result
    assert "mention_count" in dump_result
    print(f"  [PASS] YAML dump: 包含 emphasis 和 mention_count")

    # 测试 front matter
    full_content = "---\nentry_id: test-001\nemphasis: true\nmention_count: 3\n---\n\nBody content"
    fm, body = extract_front_matter(full_content)
    assert fm.get("emphasis") == True
    assert fm.get("mention_count") == 3
    assert body.strip() == "Body content"
    print(f"  [PASS] Front matter 解析: emphasis=True, mention_count=3")

    print("  === YAML 解析器全部通过 ===")


def test_read_memory():
    """测试读取单条记忆"""
    print("\n=== 测试 read_memory ===")

    # 先添加
    r = add_memory(
        category="habit",
        content="用户喜欢用中文沟通",
        priority="high",
        tags=["语言偏好"],
        emphasis=True,
        memory_dir=TEST_DIR,
    )
    assert r["success"]

    # 读取
    read_result = read_memory(r["file_path"], memory_dir=TEST_DIR)
    assert read_result["success"], f"读取失败: {read_result}"
    assert read_result["emphasis"] == True, f"emphasis应为True: {read_result.get('emphasis')}"
    assert read_result["category"] == "habit"
    assert "中文" in read_result["content"]
    print(f"  [PASS] 读取habit(强调): emphasis={read_result['emphasis']}, category={read_result['category']}")

    print("  === read_memory 全部通过 ===")


def test_end_to_end_weighted_search():
    """端到端测试：创建多条不同类型记忆，验证加权检索排序"""
    print("\n=== 端到端测试: 加权检索排序 ===")

    # 清理测试目录，重新开始
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    setup_test_env()

    # 创建各类记忆
    add_memory(category="skill", content="基础Python脚本编写方法", priority="low",
               tags=["Python"], memory_dir=TEST_DIR)  # 低权重skill
    add_memory(category="habit", content="偏好使用暗色主题", priority="medium",
               tags=["UI风格"], memory_dir=TEST_DIR)  # 中等权重habit
    add_memory(category="project", content="数据分析平台架构设计", priority="high",
               tags=["架构"], emphasis=True, project_name="data_platform",
               memory_dir=TEST_DIR)  # 高权重project+强调
    add_memory(category="habit", content="必须使用TypeScript编写代码", priority="high",
               tags=["代码风格"], emphasis=True, memory_dir=TEST_DIR)  # 高权重habit+强调
    add_memory(category="skill", content="React性能优化高级模式", priority="medium",
               tags=["React", "性能优化"], mention_count=5,
               memory_dir=TEST_DIR)  # 中等权重skill+反复提及

    # 搜索所有
    results = search_memory(query="", memory_dir=TEST_DIR)

    print(f"\n  加权检索排序结果（共{len(results)}条）:")
    for i, r in enumerate(results):
        emp = " [强调]" if r.get("emphasis") else ""
        mc = f" [提及{r.get('mention_count',0)}次]" if r.get("mention_count", 0) > 0 else ""
        print(f"    [{i+1}] weight={r['weight']:5.1f} | {r['category']:7s} | {r['priority']:6s}{emp}{mc} | {r['summary']}")

    # 验证排序
    if len(results) >= 2:
        for i in range(len(results) - 1):
            assert results[i]["weight"] >= results[i+1]["weight"], \
                f"排序错误: 第{i+1}条权重({results[i]['weight']}) < 第{i+2}条({results[i+1]['weight']})"

    # project+high+emphasis 应该最高
    if results:
        top = results[0]
        # project+high+emphasis+近期 应该是最高权重
        expected_max = compute_weight("project", "high", emphasis=True, date_str=now_iso())
        assert top["weight"] == expected_max, \
            f"最高权重应为{expected_max}，实际为{top['weight']}"
        print(f"\n  [PASS] 最高权重验证: weight={top['weight']} (project+high+emphasis+近期)")

    print("\n  === 端到端测试全部通过 ===")


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("StructuredMemoryManager - 加权检索功能测试")
    print("=" * 60)

    try:
        setup_test_env()

        # 核心算法测试
        test_compute_weight()
        test_resolve_conflict()
        test_yaml_parser()

        # 功能测试
        test_add_memory()
        test_read_memory()
        test_search_memory_weighted()
        test_confirm_memory()
        test_rebuild_index()

        # 规范验证测试
        test_weight_priority_rules()

        # 端到端测试
        test_end_to_end_weighted_search()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! 所有测试通过!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 运行错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cleanup_test_env()
