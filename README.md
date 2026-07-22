# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。

## 简介

StructuredMemoryManager 是一个全面接管 Agent 记忆生成、存储、索引和检索行为的 Skill 包。它替代默认的按时间分文件记忆方式，提供：

- **三分类存储**：习惯偏好、技能方法、项目详情分而治之
- **独立文件**：每条记忆一个 `.md` 文件，按类别存入子目录
- **YAML 结构化索引**：全局 `memory_index.md` 维护所有条目的元数据
- **加权二级检索**：总目录粗筛 → 独立文件精读，差异化权重排序，高效精准
- **强调与提及追踪**：用户主动强调的内容和反复提及的技能获得最高权重
- **优先级与保鲜期**：高优记忆永不丢失，临时信息自动过期
- **自动归档**：超阈值时自动归档低优先级旧条目
- **统一 CLI 入口**：所有操作通过 `cli.py` 执行，Agent 无需直接调用 Python 函数

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # Skill 主定义（入口）
├── prompts/
│   └── system.md              # Agent 持久化系统指令
├── scripts/
│   ├── cli.py                 # ★ 统一调度入口（Agent 唯一调用入口）
│   ├── _base.py               # 共享基础模块（YAML解析、加权算法、文件管理）
│   ├── add_memory.py          # 添加记忆（cli.py 内部调用）
│   ├── search_memory.py       # 检索记忆（cli.py 内部调用）
│   ├── confirm_memory.py      # 确认/更新记忆（cli.py 内部调用）
│   └── rebuild_index.py       # 重建索引（cli.py 内部调用）
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
- 创建记忆目录及 `habits/`、`skills/`、`projects/` 子目录
- 从模板初始化 `memory_index.md`
- 扫描高优先级标签并预加载
- 扫描 `emphasis=true` 的记忆条目，确保优先纳入上下文

### 记忆目录位置

按以下优先级自动检测：

1. `~/.trae-cn/memory/StructuredMemoryManager/`（Trae 环境）
2. `~/.cursor/memory/StructuredMemoryManager/`（Cursor 环境）
3. `~/.agent-memory/StructuredMemoryManager/`（默认）

所有项目、所有对话共享同一份记忆文件。

### 验证安装

```bash
python scripts/cli.py add -c habit --content "测试记忆" -p high -t "测试" --emphasis --json
python scripts/cli.py search "测试" --json
```

## 使用方式

### 对于 Agent（自动）

加载 Skill 后，Agent 会自动：
1. 读取 `prompts/system.md` 作为行为准则
2. 定位 `scripts/cli.py` 的绝对路径
3. 所有记忆操作通过 Shell 执行 `cli.py` 完成
4. 禁止直接使用文件工具写入记忆文件

### 什么时候该调用这个 Skill？（使用场景速查）

#### 写入记忆 — `cli.py add`

| 触发信号 | 示例 | 命令 |
|---------|------|------|
| 用户表达偏好/习惯 | "我喜欢简洁的代码"、"不要用emoji" | `python "{CLI}" add -c habit -p high ...` |
| 用户主动强调 | "记住这个"、"这个很重要" | `python "{CLI}" add -c habit --emphasis ...` |
| 完成任务后总结方法 | "这个React优化模式可以记下来" | `python "{CLI}" add -c skill -p medium ...` |
| 用户反复提及某技能 | 多次提到某个框架/方法 | `python "{CLI}" add -c skill --mention-count N ...` |
| 项目中做出重要决策 | "决定用PostgreSQL" | `python "{CLI}" add -c project -p high --project-name "xxx" ...` |
| 出现临时约定/要求 | "本次任务用Tab缩进" | `python "{CLI}" add -p low ...` |

**典型对话示例**：

```bash
# 用户强调的偏好 → --emphasis
python "{CLI}" add \
  -c habit \
  --content "用户明确要求不要使用emoji符号" \
  -p high -t "交互风格" \
  --emphasis --json

# 反复提及的技能 → --mention-count
python "{CLI}" add \
  -c skill \
  --content "React Hooks性能优化模式..." \
  -p medium -t "React,性能优化" \
  --mention-count 4 --json

# 项目关键决策
python "{CLI}" add \
  -c project \
  --content "选择PostgreSQL作为主数据库" \
  -p high -t "技术选型,数据库" \
  --project-name "data_platform" --emphasis --json
```

#### 检索记忆 — `cli.py search`

| 触发信号 | 示例 | 命令 |
|---------|------|------|
| 新对话开始 | 需要加载用户的历史偏好和约束 | `python "{CLI}" search "偏好" --high-priority --json` |
| 用户问过往信息 | "我之前说过什么？" | `python "{CLI}" search "..." --json` |
| 执行任务前检查约束 | 要生成图片前检查是否允许 | `python "{CLI}" search "图片" --high-priority --json` |
| 查找历史经验 | 类似任务需要参考之前的做法 | `python "{CLI}" search "关键词" -t "标签" --json` |
| 项目进展查询 | "我的项目现在什么状态？" | `python "{CLI}" search "进展" --category project --json` |

**检索结果按加权权重降序排列**，高权重记忆优先纳入上下文。

#### 读取单条记忆 — `cli.py read`

search 返回的 `content_snippet` 被截断时，用 read 获取完整正文：

```bash
python "{CLI}" read "habits/xxx.md" --json
```

#### 维护记忆 — `cli.py confirm` / `cli.py rebuild`

| 操作 | 命令 | 说明 |
|------|------|------|
| `confirm` | `python "{CLI}" confirm "<path>" "<id>" confirm --json` | 确认某条记忆仍有效，设为永不过期 |
| `extend` | `python "{CLI}" confirm "<path>" "<id>" extend -e "2028-01-01" --json` | 延长有效期 |
| `upgrade` | `python "{CLI}" confirm "<path>" "<id>" upgrade -p high --json` | 升为 high，永不归档 |
| `downgrade` | `python "{CLI}" confirm "<path>" "<id>" downgrade -p low --json` | 降为 low，纳入归档候选 |
| `emphasize` | `python "{CLI}" confirm "<path>" "<id>" emphasize --json` | 标记为用户主动强调/重点 |
| `de_emphasize` | `python "{CLI}" confirm "<path>" "<id>" de_emphasize --json` | 取消强调标记 |
| `bump_mention` | `python "{CLI}" confirm "<path>" "<id>" bump_mention --json` | 增加提及次数 |
| `rebuild` | `python "{CLI}" rebuild --json` | 索引与正文不一致时全量重建 |

### 对于开发者（手动测试）

可通过命令行直接测试工具，既支持统一入口也支持独立脚本：

```bash
# 方式一：统一入口（推荐）
python scripts/cli.py add -c habit --content "用户偏好深色主题" -p high -t "UI风格" --emphasis --json
python scripts/cli.py search "UI风格" --category habit --json
python scripts/cli.py confirm "habits/xxx.md" "2026-07-18-12-00-001" emphasize --json
python scripts/cli.py rebuild --json

# 方式二：独立脚本（兼容旧版）
python scripts/add_memory.py --category habit --content "用户偏好深色主题" --priority high --tags "UI风格" --emphasis
python scripts/search_memory.py search "UI风格" --category habit
python scripts/confirm_memory.py "habits/xxx.md" "2026-07-18-12-00-001" emphasize
python scripts/rebuild_index.py --all
```

## 核心工具方法

| 方法 | CLI 命令 | 功能 | 触发时机 |
|------|---------|------|---------|
| `add_memory()` | `cli.py add` | 添加记忆并维护索引 | Agent 需要持久化信息时 |
| `search_memory()` | `cli.py search` | 加权二级检索记忆 | Agent 需要回忆信息时 |
| `read_memory()` | `cli.py read` | 读取单条记忆完整内容 | 需要查看某条记忆的详情 |
| `confirm_memory()` | `cli.py confirm` | 确认/更新记忆状态 | 维护、到期确认、优先级调整、强调标记 |
| `rebuild_index()` | `cli.py rebuild` | 重建文件索引 | 索引与正文不一致时修复 |

## 记忆分类

| 分类 | 标识 | 存储目录 | 适用内容 | 文件命名 |
|------|------|---------|---------|---------|
| 习惯偏好 | `habit` | `habits/` | 交互风格、审美倾向、语言习惯 | `{摘要简写}_{序号}.md` |
| 技能方法 | `skill` | `skills/` | 工具用法、工作流、代码模式 | `{摘要简写}_{序号}.md` |
| 项目详情 | `project` | `projects/` | 项目目标、状态、决策日志 | `{项目名}.md` |

每条记忆以独立 `.md` 文件存储，包含 YAML front matter 和 Markdown 正文。同项目的多条记忆追加到同一文件。

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
| 关键词匹配分 | summary匹配+3/词, tag匹配+2/词 | 检索关键词命中加分 |
| 过期惩罚 | -5 | 已过期的条目减分 |

### 二级检索流程

1. **第一级（粗筛）**：读 `memory_index.md` 的 entries → 关键词匹配 summary/tags → 类别/标签/高优过滤 → 计算权重 → 取前10候选
2. **第二级（精读）**：打开候选文件 → 从 front matter 精确计算权重 → 提取正文片段(<=300字符) → 去冲突 → 返回前10条

### 冲突解决

- 同一分类内，高优先级记忆必须优先纳入上下文
- 低优先级记忆不可覆盖、抵消高权重记忆内容
- 若出现记忆冲突，直接采信层级权重更高的信息

### emphasis 与 mention_count

| 字段 | 适用范围 | 说明 |
|------|---------|------|
| `emphasis` | 全部分类 | 用户主动强调/标记重点（如"记住这个"、"很重要"） |
| `mention_count` | skill 类别 | 记录提及次数，>=3 视为"反复提及"，检索时获得最高子权重 |

```bash
# 记录用户强调的偏好
python "{CLI}" add -c habit --content "必须用中文回复" -p high --emphasis --json

# 记录反复提及的技能
python "{CLI}" add -c skill --content "React Hooks优化模式" -p medium --mention-count 4 --json
```

## 优先级体系

| 级别 | 行为 | 典型场景 |
|------|------|---------|
| `high` | 永不归档，启动时预加载 | 硬性约束（如"不要生成图片"） |
| `medium` | 正常保留，到期提示确认 | 稳定偏好（如"用暗色主题"） |
| `low` | 90天后纳入归档候选 | 临时信息（如"本次用Tab"） |

## 归档机制

- **触发条件**：类别下 `.md` 文件数 > 50
- **筛选条件**：`priority == low` 且距今 > 90 天；若归档后仍超阈值，降低至 60 天再筛选
- **归档动作**：移至 `archive/` 子目录，总目录索引同步更新路径
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

### 总目录索引格式

```markdown
---
last_modified: "2026-07-19T12:00:00+08:00"
entries:
  - path: "habits/no_emoji_001.md"
    category: habit
    summary: "用户明确要求永远不要使用emoji"
    priority: high
    tags: [交互风格, emoji]
    entry_id: "2026-07-19-12-00-001"
    last_modified: "2026-07-19T12:00:00+08:00"
    emphasis: true
---
```

## 存储结构

```
{MEMORY_DIR}/
├── memory_index.md                    # 总目录索引（YAML entries 列表）
├── habits/
│   ├── {摘要简写}_{序号}.md           # 每条记忆一个独立文件
│   └── archive/                       # 归档子目录
├── skills/
│   ├── {摘要简写}_{序号}.md
│   └── archive/
└── projects/
    ├── {项目名}.md                     # 同项目追加条目到同一文件
    └── archive/
```

## 运行测试

```bash
# 验证模块可导入
python -c "from add_memory import add_memory; from search_memory import search_memory; print('OK')"

# 端到端测试
python scripts/cli.py add -c habit --content "测试记忆" -p high -t "测试" --emphasis --json
python scripts/cli.py search "测试" --json
python scripts/cli.py rebuild --json
```

## 依赖

| 依赖 | 版本要求 | 必需 | 说明 |
|------|---------|------|------|
| Python | >=3.8 | 是 | 运行环境 |
| PyYAML | >=5.0 | 推荐 | YAML解析，无则启用内置简易解析器 |

## 设计文档

- [使用案例](references/usage_examples.md) - 8个典型场景的完整操作演示
- [Schema 参考](references/schema_guide.md) - 所有 YAML 字段的类型定义与规范
- [最佳实践](references/best_practices.md) - 设计思路、优先级策略、归档原理

## 许可证

MIT License

---

## 更新日志

### v2.0.0 (2026-07-23)

**CLI 统一入口与 Agent 执行方式改造**

- **新增 `cli.py` 统一调度入口**：5个子命令 `add/search/read/confirm/rebuild`，Agent 通过 Shell 执行 `python cli.py <command>` 完成所有记忆操作，不再直接调用 Python 函数
- **SKILL.md 精简**：从 10.7KB 精简至 3.2KB，移除与 system.md 重复的命令细节，只保留元数据 + 触发场景 + 加载指令
- **system.md 更新**：所有使用场景从抽象函数签名改为具体 Shell 命令模板
- **references/ 全面更新**：best_practices、schema_guide、usage_examples 三个文件重写，匹配当前独立文件架构，移除过时的单文件架构描述（`internal_index`、`priority_tags`、三级检索等）

**设计理由**：Skill 工具加载后 Agent 只能看到文档文本，无法直接调用 Python 函数。将抽象调用映射为 Shell 命令模板后，Agent 能机械执行而无需猜测调用方式。

