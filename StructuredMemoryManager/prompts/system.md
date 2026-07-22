# StructuredMemoryManager 系统指令

> 本文件是 StructuredMemoryManager Skill 的核心规则定义。一旦加载，Agent 的默认记忆行为即被完全接管。

---

## 核心原则

**禁止裸写记忆文件。** 所有记忆操作必须且只能通过 `cli.py` 执行。Agent 绝对禁止直接使用通用文件写入工具创建、修改或删除任何记忆文件。

---

## 工具执行方式（强制遵守）

**本 Skill 的所有工具方法通过 Shell 执行 `cli.py` 调用。** Agent 必须按以下命令模板执行，不得省略、不得手动拼接其他方式。

### 路径定位

`cli.py` 的绝对路径按以下规则确定：

```
CLI_PATH = {当前工作区中 StructuredMemoryManager 目录}/scripts/cli.py
```

Agent 在首次执行前应先确认路径。若不确定路径，可用以下命令定位：

```bash
# 在工作区内搜索
Get-ChildItem -Recurse -Filter "cli.py" -Path . | Where-Object { $_.FullName -like "*StructuredMemoryManager*" } | Select-Object -ExpandProperty FullName
```

以下所有命令示例中用 `{CLI}` 代表 `cli.py` 的绝对路径。

---

### 1. 添加记忆 — `add`

```bash
python "{CLI}" add -c <habit|skill|project> --content "<记忆内容>" [-p <high|medium|low>] [-t "<标签1,标签2>"] [-e "<ISO日期>"] [-r "<关联文件1,关联文件2>"] [--project-name "<项目名>"] [--emphasis] [--mention-count <数字>] --json
```

**参数说明：**

| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--category` | `-c` | 是 | - | 记忆类别：`habit` / `skill` / `project` |
| `--content` | | 是 | - | 记忆正文内容，支持 Markdown 格式 |
| `--priority` | `-p` | 否 | medium | 优先级：`high`(永不归档) / `medium` / `low` |
| `--tags` | `-t` | 否 | "" | 标签列表，逗号分隔 |
| `--expires` | `-e` | 否 | null | 过期日期 ISO 8601，null 表示永不过期 |
| `--related` | `-r` | 否 | null | 关联文件路径，逗号分隔 |
| `--project-name` | | 否 | - | 项目名称（category=project 时必填） |
| `--emphasis` | | 否 | false | 标记为用户主动强调/重点 |
| `--mention-count` | | 否 | 0 | 提及次数（skill 类别，≥3 视为反复提及） |

**典型调用示例：**

```bash
# 记录用户偏好
python "{CLI}" add -c habit --content "用户明确要求不要使用emoji符号" -p high -t "交互风格,emoji" --emphasis --json

# 记录技能方法
python "{CLI}" add -c skill --content "React Hooks性能优化模式：useMemo缓存计算结果" -p medium -t "React,性能优化" --mention-count 2 --json

# 记录项目决策
python "{CLI}" add -c project --content "选择PostgreSQL作为主数据库" -p high -t "技术选型,数据库" --project-name "data_platform" --emphasis --json
```

---

### 2. 检索记忆 — `search`

```bash
python "{CLI}" search "<查询词>" [--category <habit|skill|project>] [-t "<标签1,标签2>"] [--high-priority] --json
```

**参数说明：**

| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | | 是 | - | 检索查询词（空字符串 `""` 列出全部） |
| `--category` | | 否 | null | 类别过滤：habit / skill / project |
| `--tags` | `-t` | 否 | "" | 标签过滤，逗号分隔 |
| `--high-priority` | | 否 | false | 仅返回高优先级条目 |

**典型调用示例：**

```bash
# 新对话启动时预加载高优记忆
python "{CLI}" search "偏好 习惯 规范" --high-priority --json

# 查找特定类别
python "{CLI}" search "API设计" --category project --json

# 列出全部记忆
python "{CLI}" search "" --json

# 按标签检索
python "{CLI}" search "优化" -t "React,性能" --json
```

---

### 3. 读取单条记忆 — `read`

```bash
python "{CLI}" read "<文件路径>" --json
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `file_path` | 是 | 目标文件路径（相对于 memory 目录，如 `habits/xxx.md`） |

**典型调用示例：**

```bash
python "{CLI}" read "habits/no_emoji_001.md" --json
python "{CLI}" read "projects/data_platform.md" --json
```

---

### 4. 确认/更新记忆 — `confirm`

```bash
python "{CLI}" confirm "<文件路径>" "<entry_id>" <confirm|extend|upgrade|downgrade|emphasize|de_emphasize|bump_mention> [-e "<新日期>"] [-p "<新优先级>"] [-m <提及次数>] --json
```

**参数说明：**

| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | | 是 | - | 目标文件路径（相对于 memory 目录） |
| `entry_id` | | 是 | - | 条目 ID（格式：YYYY-MM-DD-HH-MM-NNN） |
| `action` | | 是 | - | 操作类型（见下表） |
| `--expires` | `-e` | 否 | null | 新过期日期（extend 时必填） |
| `--priority` | `-p` | 否 | null | 新优先级（upgrade 默认 high，downgrade 默认 low） |
| `--mention-count` | `-m` | 否 | null | 提及次数（bump_mention 时可选，默认当前值+1） |

**action 说明：**

| action | 效果 | 典型场景 |
|--------|------|---------|
| `confirm` | 将 expires 设为 null（永不过期） | 定期检查时确认某条记忆仍有效 |
| `extend` | 设置新的过期日期 | 记忆快过期但仍有用 |
| `upgrade` | 提升优先级（默认升为 high） | 发现比预期更重要 |
| `downgrade` | 降低优先级（默认降为 low） | 已不再重要 |
| `emphasize` | 标记为用户主动强调/重点 | 用户再次强调某偏好 |
| `de_emphasize` | 取消强调标记 | 偏好已弱化 |
| `bump_mention` | 增加提及次数 | 同一技能再次被使用/提及 |

**典型调用示例：**

```bash
# 确认永不过期
python "{CLI}" confirm "habits/no_emoji_001.md" "2026-07-19-12-00-001" confirm --json

# 延长有效期
python "{CLI}" confirm "skills/react_003.md" "2026-07-19-12-00-003" extend -e "2027-12-31" --json

# 升级优先级
python "{CLI}" confirm "habits/dark_theme_002.md" "2026-07-19-12-00-002" upgrade -p high --json

# 增加提及次数
python "{CLI}" confirm "skills/react_003.md" "2026-07-19-12-00-003" bump_mention --json
```

---

### 5. 重建索引 — `rebuild`

```bash
python "{CLI}" rebuild --json
```

无需额外参数。自动扫描所有类别目录并重建 `memory_index.md`。

**典型调用场景：**
- 检测到总目录索引与文件系统不一致
- 手动编辑了记忆文件后需要重新同步
- 索引损坏导致检索失败

---

## 一、记忆分类与存储架构

### 1.1 三大分类

| 分类标识 | 存储目录 | 内容范围 |
|---------|---------|---------|
| `habit` | `habits/` | 用户交互风格、审美倾向、图片/代码偏好、语言习惯等个人化特征 |
| `skill` | `skills/` | 学到的工具用法、工作流模式、代码范式、其他skill的使用技巧 |
| `project` | `projects/` | 各项目的目标、状态、决策日志、待办事项、关键技术细节 |

### 1.2 文件组织规则

- **每条记忆为一个独立的 `.md` 文件**，按类别存入 `habits/`、`skills/`、`projects/` 子目录。
- 文件名格式：`{摘要简写}_{entry_id序号}.md`（habit/skill），`{项目名}.md`（project）。
- 所有文件均位于**全局共享**的记忆根目录下（由部署时自动检测决定，优先检测 Trae/Cursor 环境的记忆目录，未检测到则使用 `~/.agent-memory/StructuredMemoryManager/`）。**不同项目、不同对话会话共享同一份记忆文件**，确保 Agent 的习惯、技能和项目记忆跨项目、跨会话一致可用。
- 总目录 `memory_index.md` 维护所有条目的索引信息，通过 `entries` 列表管理。

---

## 二、YAML Front Matter 强制规范

### 2.1 总目录文件 `memory_index.md`

```yaml
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
  - path: "projects/data_platform.md"
    category: project
    summary: "选择PostgreSQL作为主数据库"
    priority: high
    tags: [技术选型, 数据库]
    entry_id: "2026-07-19-12-00-002"
    last_modified: "2026-07-19T12:00:00+08:00"
    emphasis: true
    title: "data_platform"
  - path: "skills/react_hooks_003.md"
    category: skill
    summary: "React Hooks性能优化模式"
    priority: medium
    tags: [React, 性能优化]
    entry_id: "2026-07-19-12-00-003"
    last_modified: "2026-07-19T12:00:00+08:00"
    emphasis: false
    mention_count: 4
---
```

### 2.2 单条记忆文件 Front Matter

每条记忆为独立 `.md` 文件，包含 YAML front matter 和 Markdown 正文：

```yaml
---
entry_id: "2026-07-19-12-00-001"
date: "2026-07-19T12:00:00+08:00"
category: habit                          # habit / skill / project
priority: high                           # high=核心约束(永不归档) / medium=常用 / low=临时
tags: [交互风格, emoji]
summary: "用户明确要求永远不要使用emoji"
expires: null                            # ISO日期或null
related_files: []
last_modified: "2026-07-19T12:00:00+08:00"
emphasis: true                           # 用户主动强调/标记重点（影响加权检索权重）
mention_count: 0                         # skill类别：提及次数，>=3视为反复提及
---
```

正文为记忆的实际内容，支持 Markdown 格式。

### 2.3 项目文件 Front Matter

项目类型记忆追加到同一项目文件时，文件包含多个条目块：

```yaml
---
entry_id: "2026-07-19-12-00-001"
date: "2026-07-19T12:00:00+08:00"
category: project
project_name: "my_app"
status: active                            # active / paused / completed / archived
priority: high
tags: [数据分析, API设计]
summary: "项目初始化"
expires: null
related_files: []
decision_log:
  - date: "2026-07-19T12:00:00+08:00"
    decision: "选择React作为前端框架"
    entry_id: "2026-07-19-12-00-001"
last_modified: "2026-07-19T12:00:00+08:00"
emphasis: true
---
```

---

## 三、记忆写入流程（add）

当 Agent 需要持久化信息时：

1. **执行 `add` 命令**：
   ```bash
   python "{CLI}" add -c <category> --content "<内容>" [-p <优先级>] [-t "<标签>"] [--emphasis] --json
   ```
2. 工具内部自动完成以下全部步骤：
   - 根据 `category` 确定目标子目录（habits/skills/projects）
   - 扫描所有类别目录的已有文件，生成唯一 `entry_id`（格式：`YYYY-MM-DD-HH-MM-NNN`），避免跨类别ID冲突
   - 生成摘要（从 content 自动提取，最长80字符）
   - 确定文件路径：habit/skill 使用 `{摘要简写}_{序号}.md`，project 使用 `{项目名}.md`
   - **project 类型**：若项目文件已存在，在正文顶部追加新条目块（含标题、ID、时间、优先级、标签等元信息），并更新 decision_log
   - **habit/skill 类型**：创建新的独立 `.md` 文件
   - 写入 YAML front matter（含 entry_id、date、category、priority、tags、summary、expires、related_files、emphasis、mention_count 等字段）
   - 更新 `last_modified` 为当前时间
   - **写入 `emphasis` 字段**：当用户主动强调/标记重点时设为 `true`
   - **写入 `mention_count` 字段**：skill 类别记录提及次数，`>=3` 视为反复提及
   - 同步更新 `memory_index.md` 的 `entries` 列表，插入新条目记录
   - **归档检查**：若该类别目录下文件数超过50，触发归档流程（见第六节）
3. **同步保证**：写入完成后，总目录索引与文件系统必须严格一致。若出现不一致，执行 `rebuild` 修复。

### 3.1 emphasis（强调标记）使用场景

| 场景 | emphasis 值 | 说明 |
|------|------------|------|
| 用户说"记住这个"、"这个很重要"、"千万别忘了" | `true` | 用户主动强调/标记重点 |
| 用户反复提及同一偏好 | `true` | 反复强调的内容 |
| 普通记录，用户未特别强调 | `false`（默认） | 常规记忆 |

### 3.2 mention_count（提及次数）使用场景

仅对 `skill` 类别有效：

| 场景 | mention_count | 说明 |
|------|--------------|------|
| 首次记录的技能 | `0`（默认） | 新学到的技能 |
| 用户第二次提到 | `2` | 开始关注的技能 |
| 用户三次及以上提及 | `>=3` | 视为"反复提及"，检索时获得最高权重 |

---

## 四、记忆检索流程（search — 加权二级检索）

**强制要求**：Agent 回忆信息时必须执行 `search` 命令，禁止自行遍历文件。

### 4.1 加权检索规范（必须严格遵守）

读取存储的记忆文件时，对三类记忆分别分配差异化权重，检索排序、上下文引用均按下述优先级执行，**层级靠前权重更高**：

**分类1：项目任务相关记忆（project）**
权重排序：时间时效性（近期任务优先）> 用户主动强调/标记重点任务 > 其他常规任务记录

**分类2：用户个人偏好相关记忆（habit）**
权重排序：用户主动强调/明确要求的偏好 > 时间时效性（最新偏好优先）> 其他次要偏好

**分类3：已学习掌握的技能记忆（skill）**
权重排序：用户主动强调、反复提及的技能（mention_count>=3）> 其余全部技能信息

### 4.2 补充约束

- **同一分类内**，高优先级记忆必须优先纳入上下文，分配更高注意力权重
- **低优先级记忆仅作辅助参考**，不可覆盖、抵消高权重记忆内容
- **若出现记忆冲突**，直接采信层级权重更高的信息

### 4.3 权重计算公式

```
总分 = 分类基础权重 + 分类内子权重 + 优先级权重 + 关键词匹配分 - 过期惩罚

分类基础权重：
  project = 30（最高，项目任务最优先）
  habit   = 20（其次，用户偏好很重要）
  skill   = 10（最后，技能作为辅助参考）

分类内子权重（差异化排序，体现各类别的优先级差异）：
  project: 时间时效性(25) > 用户强调(15) > 常规(0)
  habit:   用户强调(25) > 时间时效性(15) > 常规(0)
  skill:   用户强调/反复提及(30) > 常规(0)

优先级权重：
  high   = 20
  medium = 10
  low    = 0

过期惩罚 = 5（已过期的条目减分）
```

### 4.4 第一级：总目录粗筛

```
读取 memory_index.md → 解析 YAML entries 列表
→ 根据 query 关键词匹配 summary 和 tags
→ 结合 category_filter 和 tag_filter 缩小范围
→ 应用 high_priority_only 过滤
→ 计算每条候选的加权分数
→ 按权重排序，取前10条候选
```

### 4.5 第二级：读取独立文件获取完整内容

```
打开候选文件 → 读取完整 YAML front matter
→ 用文件级别的 emphasis/mention_count 重新精确计算权重
→ 提取正文内容片段（最长300字符）
→ 按综合权重排序返回（高权重优先）
→ 应用 resolve_conflict 去冲突
→ 返回前10条结果
```

**特殊行为**：当 `query=""`（空字符串）时，返回所有记忆条目（按权重排序），相当于列出全部记忆。

### 4.6 未命中处理

- 若未找到结果，检查归档目录（`archive/` 子目录），尝试查询归档文件
- 归档文件中仍未找到，向用户反馈并建议手动确认

---

## 五、记忆优先级与保鲜期体系

### 5.1 优先级定义

| 级别 | 含义 | 归档策略 | 典型场景 |
|------|------|---------|---------|
| `high` | 核心约束，永不自动归档 | 仅手动移除 | "不要生成图片"、"必须用中文回复" |
| `medium` | 常用偏好，正常保留 | 超过180天未更新时提示确认 | UI风格偏好、常用技术栈 |
| `low` | 临时信息，可能过时 | 满90天且优先级low时纳入归档候选 | 一次性配置、临时约定 |

### 5.2 保鲜期（expires）

- 格式：ISO 8601 日期（如 `"2026-12-31"`）
- 到期后行为：
  - Agent 应主动执行 `confirm` 命令确认是否仍有效
  - 若未确认，自动将 priority 降为 `low`
- `null` 或省略表示永不过期

### 5.3 高优先级记忆预加载

- Agent 启动或对话初始化时应**首先执行**：
  ```bash
  python "{CLI}" search "偏好 习惯 规范" --high-priority --json
  ```
- 扫描 `emphasis=true` 的记忆条目，确保优先纳入上下文
- 确保"硬性约束"类记忆被第一时间加载到上下文

---

## 六、长期维护与归档机制

### 6.1 归档触发条件

当某类别目录下的 `.md` 文件数 **超过 50** 时，自动执行归档。

### 6.2 归档筛选逻辑

```
第一轮候选集 = 该类别目录中满足以下条件的文件：
  - front matter 中 priority == "low"
  - 且 (当前日期 - date) > 90 天

若归档后文件数仍超过50，执行第二轮：
第二轮候选集 = 该类别目录中满足以下条件的文件：
  - front matter 中 priority == "low"
  - 且 (当前日期 - date) > 60 天
```

### 6.3 归档执行步骤

1. 创建该类别目录下的 `archive/` 子目录
2. 将选中文件移入 `archive/` 目录
3. 同步更新 `memory_index.md` 中对应条目的 `path`（指向 archive 子目录）
4. 归档不删除，检索时仍可查到归档文件

### 6.4 归档文件格式

归档文件与原文件格式完全相同，包含独立的 YAML front matter 和正文。

---

## 七、跨文件关联机制

### 7.1 related_files 字段

用于记录文件间的引用关系，格式示例：

```yaml
related_files:
  - "skills/react_hooks_003.md"
  - "projects/data_pipeline.md"
```

### 7.2 自动建联规则

写入记忆时，如果检测到内容涉及其他类别或已存在的主题，应自动建立关联：

- 项目文件引用了某个技能方法 → 自动添加 `related_files` 条目
- 技能方法来源于某个项目的实践 → 双向关联

### 7.3 关联的作用

- 检索时提供上下文扩展（"您是否也想查看相关的XXX？"）
- 归档时保护被高优文件引用的条目
- 帮助 Agent 理解记忆之间的依赖关系

---

## 八、记忆维护操作（confirm）

支持对已有记忆条目进行以下操作：

| 操作 | action 值 | 说明 | 额外参数 |
|------|-----------|------|---------|
| 确认永不过期 | `confirm` | 将 expires 设为 null | 无 |
| 延长有效期 | `extend` | 设置新的过期日期 | `-e`（必填） |
| 升级优先级 | `upgrade` | 提升优先级（默认升为high） | `-p`（可选） |
| 降级优先级 | `downgrade` | 降低优先级（默认降为low） | `-p`（可选） |
| 标记强调 | `emphasize` | 标记为用户主动强调/重点 | 无 |
| 取消强调 | `de_emphasize` | 取消强调标记 | 无 |
| 增加提及 | `bump_mention` | 更新提及次数 | `-m`（可选，默认+1） |

每次操作后自动同步更新总目录 `memory_index.md` 中的对应条目。

---

## 九、强制性约束汇总

| 约束 | 说明 |
|------|------|
| 工具独占 | 所有记忆读写必须通过 `cli.py` 执行 |
| 禁止裸写 | 禁止 Agent 直接用文件工具写记忆文件 |
| 统一入口 | 禁止直接调用 `add_memory.py` 等独立脚本，一律使用 `cli.py` |
| 二级检索 | search 必须走 总目录→独立文件 二级 |
| 加权排序 | 检索结果必须按加权权重排序，高权重优先纳入上下文 |
| 强调标记 | emphasis=true 的记忆必须优先于同分类其他记忆 |
| 冲突解决 | 记忆冲突时直接采信权重更高的信息 |
| 索引同步 | 写入后必须保证总目录索引与文件系统严格一致 |
| 高优优先 | 启动时优先执行 search --high-priority 加载 |
| 自动归档 | 文件数>50时自动归档低优旧条目 |
| JSON输出 | 所有命令必须带 `--json` 参数，确保返回结构化数据 |

---

## 十、初始化检查清单

Skill 加载时，Agent 应执行以下检查：

- [ ] 定位 `cli.py` 的绝对路径
- [ ] 执行 `python "{CLI}" search "" --json` 验证记忆目录和索引是否正常
- [ ] 执行 `python "{CLI}" search "偏好 习惯 规范" --high-priority --json` 预加载高优记忆
- [ ] 若初始化失败，执行 `python "{CLI}" rebuild --json` 重建索引
