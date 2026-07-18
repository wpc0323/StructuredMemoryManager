# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。

## 简介

StructuredMemoryManager 是一个全面接管 Agent 记忆生成、存储、索引和检索行为的 Skill 包。它替代默认的按时间分文件记忆方式，提供：

- **三分类存储**：习惯偏好、技能方法、项目详情分而治之
- **YAML 结构化索引**：每个文件都有完整的元数据和内部索引
- **加权三级检索**：总目录 → 内部索引 → 正文，差异化权重排序，高效精准
- **强调与提及追踪**：用户主动强调的内容和反复提及的技能获得最高权重
- **优先级与保鲜期**：高优记忆永不丢失，临时信息自动过期
- **自动归档**：超阈值时自动归档低优先级旧条目
- **跨文件关联**：记忆之间建立显式引用关系
- **记忆冲突解决**：高权重记忆优先采纳，低权重不可覆盖高权重

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # Skill 主定义（入口）
├── prompts/
│   └── system.md              # Agent 持久化系统指令
├── scripts/
│   ├── _base.py               # 共享基础模块（YAML解析、加权算法、文件管理）
│   ├── add_memory.py          # 添加记忆（可独立调用）
│   ├── search_memory.py       # 检索记忆（可独立调用）
│   ├── confirm_memory.py      # 确认/更新记忆（可独立调用）
│   ├── rebuild_index.py       # 重建索引（可独立调用）
│   └── test_weighted_search.py # 加权检索功能测试
├── templates/
│   ├── memory_index.md        # 总目录模板
│   ├── habits_template.md     # 习惯偏好模板
│   ├── skills_template.md     # 技能方法模板
│   └── project_template.md    # 项目文件模板
├── references/
│   ├── usage_examples.md      # 典型使用案例
│   ├── schema_guide.md        # YAML Schema 完全参考
│   └── best_practices.md      # 设计思路与最佳实践
├── README.md                  # 本文件
├── LICENSE                    # MIT 许可证
└── .gitignore                 # Git 忽略规则
```

## 安装

### 前置要求

- Python 3.8+
- PyYAML >= 5.0（可选，有内置回退方案）

### 安装步骤

1. 将整个 `StructuredMemoryManager/` 目录复制到 Agent 的 Skills 目录下
2. 确保 `SKILL.md` 可被 Agent 的 skill 加载器正确识别
3. （可选）安装 PyYAML 以获得更好的 YAML 解析能力：
   ```bash
   pip install pyyaml
   ```

### 首次初始化

Skill 首次加载时会自动：
- 创建 `memory/` 目录及 `habits/`、`skills/`、`projects/` 子目录
- 从模板初始化 `memory_index.md`
- 扫描高优先级标签并预加载
- 扫描 `emphasis=true` 的记忆条目，确保优先纳入上下文

### 验证安装

```bash
cd scripts
python add_memory.py --category habit --content "测试记忆" --priority high --tags 测试 --emphasis --json
python search_memory.py search "测试" --json
```

## 使用方式

### 对于 Agent（自动）

加载 Skill 后，Agent 会自动：
1. 读取 `prompts/system.md` 作为行为准则
2. 所有记忆操作路由到 `scripts/` 下对应工具方法
3. 禁止直接使用文件工具写入记忆文件

### 什么时候该调用这个 Skill？（使用场景速查）

#### 写入记忆 — 调用 `add_memory()`

| 触发信号 | 示例 | 调用方式 |
|---------|------|---------|
| 用户表达偏好/习惯 | "我喜欢简洁的代码"、"不要用emoji" | `add_memory(category="habit", priority="high")` |
| 用户主动强调 | "记住这个"、"这个很重要" | `add_memory(category="habit", emphasis=True)` |
| 完成任务后总结方法 | "这个React优化模式可以记下来" | `add_memory(category="skill", priority="medium")` |
| 用户反复提及某技能 | 多次提到某个框架/方法 | `add_memory(category="skill", mention_count=N)` |
| 项目中做出重要决策 | "决定用PostgreSQL" | `add_memory(category="project", priority="high", project_name="xxx")` |
| 出现临时约定/要求 | "本次任务用Tab缩进" | `add_memory(priority="low")` |

**典型对话示例**：

```python
# 用户强调的偏好 → emphasis=True
add_memory(
    category="habit",
    content="用户明确要求不要使用emoji符号",
    priority="high",
    tags=["交互风格"],
    emphasis=True,                    # 标记为用户主动强调
)

# 反复提及的技能 → mention_count
add_memory(
    category="skill",
    content="React Hooks性能优化模式...",
    priority="medium",
    tags=["React", "性能优化"],
    mention_count=4,                  # 用户已提及4次
    expires="2027-06-24",
)

# 项目关键决策
add_memory(
    category="project",
    content="选择PostgreSQL作为主数据库",
    priority="high",
    tags=["技术选型", "数据库"],
    project_name="data_platform",
    emphasis=True,                    # 重要决策标记强调
)
```

#### 检索记忆 — 调用 `search_memory()`

| 触发信号 | 示例 | 调用方式 |
|---------|------|---------|
| 新对话开始 | 需要加载用户的历史偏好和约束 | `search_memory(query="偏好", high_priority_only=True)` |
| 用户问过往信息 | "我之前说过什么？" | `search_memory(query="...")` |
| 执行任务前检查约束 | 要生成图片前检查是否允许 | `search_memory(query="图片", high_priority_only=True)` |
| 查找历史经验 | 类似任务需要参考之前的做法 | `search_memory(query="关键词", tag_filter=["标签"])` |
| 项目进展查询 | "我的项目现在什么状态？" | `search_memory(query="进展", category_filter="project")` |

**检索结果按加权权重降序排列**，高权重记忆优先纳入上下文。

#### 维护记忆 — 调用 `confirm_memory()` / `rebuild_index()`

| 操作 | 触发时机 | 说明 |
|------|---------|------|
| `confirm` | 定期检查时确认某条记忆仍有效 | 设为永不过期 |
| `extend` | 快过期但仍有用的记忆 | 延长有效期（如再延1年） |
| `upgrade` | 用户再次强调某偏好 / 发现比预期更重要 | 升为 high，永不归档 |
| `downgrade` | 已不再重要的旧信息 | 降为 low，纳入归档候选 |
| `emphasize` | 用户再次强调某条记忆 | 标记为用户主动强调/重点 |
| `de_emphasize` | 取消强调标记 | 恢复为普通记忆 |
| `bump_mention` | 用户再次提及某个技能 | 增加提及次数 |
| `rebuild_index` | 索引与正文不一致 / 手动编辑后修复 | 全量重建内部索引 |

### 对于开发者（手动测试）

可通过命令行直接测试工具：

```bash
# 添加一条记忆（带强调标记）
python scripts/add_memory.py \
  --category habit \
  --content "用户偏好深色主题" \
  --priority high \
  --tags "UI风格" \
  --emphasis

# 添加一条技能记忆（带提及次数）
python scripts/add_memory.py \
  --category skill \
  --content "React Hooks优化模式" \
  --priority medium \
  --tags "React,性能优化" \
  --mention-count 4

# 搜索记忆（按权重排序）
python scripts/search_memory.py search "UI风格" --category habit

# 标记记忆为强调
python scripts/confirm_memory.py "habits/xxx.md" "2026-07-18-12-00-001" emphasize

# 增加提及次数
python scripts/confirm_memory.py "skills/xxx.md" "2026-07-18-12-00-002" bump_mention --mention-count 5

# 重建索引
python scripts/rebuild_index.py --all
```

## 核心工具方法

| 方法 | 功能 | 触发时机 |
|------|------|---------|
| `add_memory()` | 添加记忆并维护索引 | Agent 需要持久化信息时 |
| `search_memory()` | 加权三级检索记忆 | Agent 需要回忆信息时 |
| `read_memory()` | 读取单条记忆完整内容 | 需要查看某条记忆的详情 |
| `confirm_memory()` | 确认/更新记忆状态 | 维护、到期确认、优先级调整、强调标记 |
| `rebuild_index()` | 重建文件索引 | 索引与正文不一致时修复 |

## 记忆分类

| 分类 | 标识 | 存储目录 | 适用内容 |
|------|------|---------|---------|
| 习惯偏好 | `habit` | `habits/` | 交互风格、审美倾向、语言习惯 |
| 技能方法 | `skill` | `skills/` | 工具用法、工作流、代码模式 |
| 项目详情 | `project` | `projects/` | 项目目标、状态、决策日志 |

每条记忆以独立 `.md` 文件存储，包含 YAML front matter 和 Markdown 正文。

## 加权检索规范

检索时对三类记忆分配差异化权重，确保高权重信息优先纳入上下文：

### 分类间基础权重

```
project (30) > habit (20) > skill (10)
```

### 分类内排序规则

| 分类 | 权重排序（高→低） | 设计理由 |
|------|------------------|---------|
| **project** | 时间时效性(25) > 用户强调(15) > 常规(0) | 项目任务近期最紧急，时效性优先 |
| **habit** | 用户强调(25) > 时间时效性(15) > 常规(0) | 用户明确要求的偏好最不可违背 |
| **skill** | 用户强调/反复提及(30) > 常规(0) | 反复提及的技能价值最高 |

### 权重计算公式

```
总分 = 分类基础权重 + 分类内子权重 + 优先级权重 + 关键词匹配分 - 过期惩罚
```

| 权重项 | 值 | 说明 |
|--------|---|------|
| 分类基础权重 | project=30, habit=20, skill=10 | 项目最优先 |
| 优先级权重 | high=20, medium=10, low=0 | 核心约束永不归档 |
| 过期惩罚 | 5 | 已过期的条目减分 |

### 冲突解决

- 同一分类内，高优先级记忆必须优先纳入上下文
- 低优先级记忆不可覆盖、抵消高权重记忆内容
- 若出现记忆冲突，直接采信层级权重更高的信息

### emphasis 与 mention_count

| 字段 | 适用范围 | 说明 |
|------|---------|------|
| `emphasis` | 全部分类 | 用户主动强调/标记重点（如"记住这个"、"很重要"） |
| `mention_count` | skill 类别 | 记录提及次数，>=3 视为"反复提及"，检索时获得最高子权重 |

```python
# 记录用户强调的偏好
add_memory(category="habit", content="必须用中文回复", priority="high", emphasis=True)

# 记录反复提及的技能
add_memory(category="skill", content="React Hooks优化模式", mention_count=4)
```

## 优先级体系

| 级别 | 行为 | 典型场景 |
|------|------|---------|
| `high` | 永不归档，启动时预加载 | 硬性约束（如"不要生成图片"） |
| `medium` | 正常保留，到期提示确认 | 稳定偏好（如"用暗色主题"） |
| `low` | 90天后纳入归档候选 | 临时信息（如"本次用Tab"） |

## 归档机制

- **触发条件**：`internal_index` 条目数 > 50
- **筛选条件**：`priority == low` 且距今 > 90 天
- **归档动作**：移至 `archive/` 子目录，原文件标记归档状态
- **可恢复性**：归档不删除，检索时可查到

## 记忆文件格式

每条记忆文件包含 YAML front matter 和 Markdown 正文：

```markdown
---
entry_id: "2026-07-18-12-00-001"
date: "2026-07-18T12:00:00+08:00"
category: habit
priority: high
tags: [交互风格, emoji]
summary: "用户明确要求永远不要使用emoji"
emphasis: true
mention_count: 0
expires: null
related_files: []
last_modified: "2026-07-18T12:00:00+08:00"
---

用户明确要求：在任何情况下都不要使用emoji符号。
```

## 运行测试

```bash
cd scripts
python test_weighted_search.py
```

测试覆盖：

- 权重计算逻辑（分类权重、子权重、优先级权重）
- 冲突解决
- YAML 解析器
- 添加/读取/检索/确认/重建索引功能
- 加权检索规范排序规则验证
- 端到端加权检索排序

## 依赖

| 依赖 | 版本要求 | 必需 | 说明 |
|------|---------|------|------|
| Python | >=3.8 | 是 | 运行环境 |
| PyYAML | >=5.0 | 推荐 | YAML解析，无则启用内置简易解析器 |

## 设计文档

- [使用案例](references/usage_examples.md) - 7个典型场景的完整操作演示
- [Schema 参考](references/schema_guide.md) - 所有 YAML 字段的类型定义与规范
- [最佳实践](references/best_practices.md) - 设计思路、优先级策略、归档原理

## 许可证

MIT License

---

## 更新日志

### v1.1.0 (2026-07-18)

**新增功能：记忆读取加权检索规范**

- **加权检索算法**：新增 `compute_weight()` 和 `resolve_conflict()` 核心函数，实现三类记忆的差异化权重排序
- **分类差异化排序规则**：
  - project：时间时效性(近期优先) > 用户强调 > 常规
  - habit：用户强调 > 时间时效性(最新优先) > 次要
  - skill：用户强调/反复提及 > 其余全部
- **emphasis 字段**：所有分类新增 `emphasis` 布尔字段，标记用户主动强调/标记重点的记忆，影响检索权重
- **mention_count 字段**：skill 分类新增 `mention_count` 整数字段，记录提及次数，>=3 视为"反复提及"
- **confirm_memory 新增操作**：
  - `emphasize`：标记为用户主动强调/重点
  - `de_emphasize`：取消强调标记
  - `bump_mention`：增加提及次数
- **search_memory 升级**：检索结果按综合权重降序排列，返回值新增 `weight`、`emphasis`、`mention_count`、`category` 字段
- **system.md 更新**：新增第四章"加权检索规范"，新增三条强制性约束（加权排序、强调标记、冲突解决）
- **memory_dir 参数传播**：`ensure_memory_dir`、`get_entry_file_path`、`read_memory_index`、`write_memory_index`、`_update_index_for_entry`、`_check_archiving` 等函数新增 `memory_dir` 参数，支持自定义记忆目录

**Bug 修复：**

- 修复跨类别 entry_id 冲突问题：`generate_entry_id` 现在扫描所有类别目录的已有文件，避免不同类别生成相同 ID 导致索引覆盖

### v1.0.0 (初始版本)

- 三分类存储：habit / skill / project
- YAML 结构化索引与 front matter 规范
- 三级检索机制：总目录 → 内部索引 → 正文
- 优先级体系（high/medium/low）与保鲜期（expires）
- 自动归档机制（阈值50条，90天低优）
- 跨文件关联（related_files）
- 四个工具方法：add_memory / search_memory / confirm_memory / rebuild_index
- PyYAML 可选依赖，内置简易 YAML 解析器回退
