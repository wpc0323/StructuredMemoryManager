# YAML Front Matter Schema 完全参考

> 本文档详细说明 StructuredMemoryManager 中所有文件类型的 YAML front matter 字段定义、类型约束和使用规范。

---

## 一、通用字段

以下字段出现在所有类型的记忆文件中：

| 字段名 | 类型 | 必填 | 说明 |
|-------|------|------|------|
| `last_modified` | string (ISO 8601) | 是 | 最后修改时间，含时区 |
| `category` | string | 是 | 分类标识：`habit` / `skill` / `project` |

### last_modified 格式规范

```yaml
# 正确格式 - 含时区偏移
last_modified: "2026-06-24T15:30:00+08:00"

# 错误格式 - 缺少时区
last_modified: "2026-06-24T15:30:00"
```

---

## 二、memory_index.md 专用字段

总目录文件用于索引所有记忆文件。

### 顶层结构

```yaml
---
last_modified: "<ISO 8601>"
files:
  - <FileEntry 对象>
---
```

### FileEntry 对象 schema

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|-------|------|------|--------|------|
| `path` | string | 是 | - | 相对于 memory 目录的文件路径 |
| `category` | string | 是 | - | habit / skill / project |
| `tags` | string[] | 是 | `[]` | 文件所有标签的并集 |
| `last_modified` | string (ISO) | 是 | - | 该文件最后修改时间 |
| `high_priority_tags` | string[] | 是 | `[]` | 高优先级标签子集，启动时优先加载 |
| `related` | string[] | 否 | `[]` | 关联的其他文件路径，支持锚点如 `file.md#section` |
| `archived` | boolean | 否 | `false` | 是否已触发归档 |
| `title` | string | 否*(project必填)* | - | 项目标题（仅 project 类别） |

### 完整示例

```yaml
---
last_modified: "2026-06-24T16:00:00+08:00"
files:
  # 习惯文件
  - path: habits_preferences.md
    category: habit
    tags: [图片偏好, 代码风格, 语言习惯, UI风格]
    last_modified: "2026-06-24T15:30:00+08:00"
    high_priority_tags: [图片偏好, 代码风格]
    related: []
    archived: false

  # 技能文件
  - path: skills_methods.md
    category: skill
    tags: [自动化, Python, React, API设计]
    last_modified: "2026-06-24T14:00:00+08:00"
    high_priority_tags: []
    related:
      - "projects/data_pipeline.md#数据处理"
    archived: false

  # 项目文件
  - path: projects/my_app.md
    category: project
    title: "MyApp数据分析平台"
    tags: [数据分析, Python, PostgreSQL, API设计]
    last_modified: "2026-06-24T12:00:00+08:00"
    high_priority_tags: [关键决策]
    related:
      - "skills_methods.md#自动化脚本"
    archived: false

  # 已归档文件示例
  - path: skills_methods.md
    category: skill
    tags: [...]
    last_modified: "2026-06-20T10:00:00+08:00"
    high_priority_tags: []
    related: []
    archived: true
---
```

---

## 三、习惯/技能文件专用字段

`habits_preferences.md` 和 `skills_methods.md` 使用相同的 front matter 结构。

### 顶层结构

```yaml
---
last_modified: "<ISO 8601>"
category: habit          # 或 skill
priority_tags: <string[]>
internal_index: <IndexEntry[]>
related_files: <string[]>
archive: <string | null>
---
```

### 字段详解

#### priority_tags (string[])

从 `internal_index` 中所有 `priority == "high"` 的条目的 `tags` 合并去重而来。
Agent 启动时首先扫描这些标签。

```yaml
priority_tags: [图片偏好, 代码风格]  # 当前活跃的高优标签集合
```

#### internal_index (IndexEntry[]) — 核心

条目级索引数组，**按时间倒序排列**（最新的在索引0位置）。

每个 IndexEntry 的 schema：

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|-------|------|------|--------|------|
| `date` | string (ISO 8601) | 是 | - | 条目创建时间 |
| `priority` | string | 是 | `"medium"` | 优先级：`high` / `medium` / `low` |
| `summary` | string | 是 | - | 内容摘要（80字以内） |
| `tags` | string[] | 是 | `[]` | 该条目标签 |
| `expires` | string \| null | 否 | `null` | 过期日期(ISO)，null=永不过期 |
| `entry_id` | string | 是 | - | 唯一ID，格式 `YYYY-MM-DD-HH-MM-NNN` |

##### IndexEntry 示例

```yaml
internal_index:
  # 高优先级条目 - 永不过期
  - date: "2026-06-24T15:30:00+08:00"
    priority: high
    summary: "用户明确要求永远不要生成图片"
    tags: ["图片偏好"]
    expires: null
    entry_id: "2026-06-24-15-30-001"

  # 中等优先级 - 有保鲜期
  - date: "2026-06-23T10:00:00+08:00"
    priority: medium
    summary: "偏好简洁UI设计，暗色主题，最小化动画效果"
    tags: ["UI风格"]
    expires: "2026-12-31"
    entry_id: "2026-06-23-10-00-001"

  # 低优先级 - 可能被归档
  - date: "2026-05-01T09:00:00+08:00"
    priority: low
    summary: "临时使用Tab缩进（已改为空格）"
    tags: ["代码格式"]
    expires: "2026-06-01"
    entry_id: "2026-05-01-09-00-001"
```

#### related_files (string[])

跨文件关联列表。支持带锚点的引用格式：

```yaml
related_files:
  - "projects/my_app.md#决策日志"
  - "skills_methods.md#API设计模式"
```

#### archive (string | null)

归档状态字段：

- `null`: 未归档（默认）
- `"habits_archive.md"` 或 `"skills_archive.md"`: 指向归档文件

---

## 四、项目文件专用字段

`projects/<name>.md` 使用略有不同的 front matter 结构。

### 顶层结构

```yaml
---
last_modified: "<ISO 8601>"
category: project
project_name: string
status: active | paused | completed | archived
priority_tags: string[]
tags: string[]
related_files: string[]
decision_log: DecisionEntry[]
---
```

### 特有字段详解

#### status (string)

项目当前生命周期状态：

| 值 | 含义 |
|---|------|
| `active` | 活跃开发中 |
| `paused` | 暂停 |
| `completed` | 已完成 |
| `archived` | 已归档 |

#### decision_log (DecisionEntry[])

替代 internal_index，专门记录项目决策。

| 字段名 | 类型 | 说明 |
|-------|------|------|
| `date` | string (date) | 决策日期 |
| `decision` | string | 决策内容简述 |
| `reason` | string | 决策原因 |

```yaml
decision_log:
  - {date: "2026-06-20", decision: "选择PostgreSQL", reason: "需要JSONB支持"}
  - {date: "2026-06-18", decision: "前端使用React", reason: "团队熟悉度高"}
```

### 项目文件完整示例

```yaml
---
last_modified: "2026-06-24T12:00:00+08:00"
category: project
project_name: data_platform
status: active
priority_tags: [关键决策, 架构设计]
tags: [数据分析, Python, PostgreSQL, REST API]
related_files:
  - "skills_methods.md#数据处理管道"
  - "skills_methods.md#自动化测试"
decision_log:
  - date: "2026-06-22"
    decision: "采用事件驱动架构处理数据流"
    reason: "需要支持多种数据源的实时接入"
  - date: "2026-06-20"
    decision: "选择PostgreSQL作为主存储"
    reason: "JSONB字段 + 全文搜索需求"
---
```

---

## 五、归档文件格式

归档文件与原文件格式相同，但用途不同：

```yaml
---
last_modified: "2026-06-24T16:00:00+08:00"
category: habit           # 或 skill
priority_tags: []         # 归档后通常为空
internal_index:           # 存放从原文件移入的低优旧条目
  - {date: "...", priority: low, summary: "...", tags: [...], expires: "...", entry_id: "..."}
related_files: []
archive: null             # 归档文件自身不再指向其他归档文件
---
```

正文中的归档条目会额外标注 `[已归档]` 和归档时间。

---

## 六、字段类型速查表

| 类型 | YAML表示 | 示例 | 说明 |
|-----|---------|------|------|
| ISO 8601 时间 | string | `"2026-06-24T15:30:00+08:00"` | 必须含时区 |
| ISO 8601 日期 | string | `"2026-12-31"` | 仅日期，用于 expires |
| 枚举字符串 | string | `"high"` / `"medium"` / `"low"` | 仅限预定义值 |
| 字符串数组 | sequence | `[tag1, tag2]` | 用方括号表示 |
| 布尔值 | boolean | `true` / `false` | 全小写 |
| 空值 | null | `null` | 表示无/未设置 |
| 内联对象 | mapping inline | `{key: value}` | 用于 decision_log 等简单对象 |

---

## 七、常见错误与纠正

### 错误1：缺少时区

```yaml
# 错误
last_modified: "2026-06-24T15:30:00"

# 正确
last_modified: "2026-06-24T15:30:00+08:00"
```

### 错误2：internal_index 未按时间倒序

```yaml
# 错误 - 旧的在前
internal_index:
  - date: "2026-01-01T..."
  - date: "2026-06-24T..."

# 正确 - 最新的在前面（index 0）
internal_index:
  - date: "2026-06-24T..."   # <-- 最新
  - date: "2026-01-01T..."   # <-- 最旧
```

### 错误3：priority_tags 与 internal_index 不同步

```yaml
# 错误 - priority_tags 包含非 high 优先级的标签
priority_tags: [所有标签都在这里]

# 正确 - 只包含 high 优先级条目的标签
priority_tags: [只有high级别条目的标签]
```

### 错误4：entry_id 格式不规范

```yaml
# 错误
entry_id: "entry_001"
entry_id: "1687610000"

# 正确
entry_id: "2026-06-24-15-30-001"
```
