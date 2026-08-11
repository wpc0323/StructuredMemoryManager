# YAML Front Matter Schema 参考

> 本文档详细说明 StructuredMemoryManager 中所有文件类型的 YAML front matter 字段定义。

---

## 一、单条记忆文件

每条记忆为独立的 `.md` 文件，包含 YAML front matter 和 Markdown 正文。

### 通用字段（habit / skill / project）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `entry_id` | string | 是 | - | 唯一ID，格式 `YYYY-MM-DD-HH-MM-NNN` |
| `date` | string (ISO 8601) | 是 | - | 创建时间，含时区 |
| `category` | string | 是 | - | `habit` / `skill` / `project` |
| `priority` | string | 是 | medium | `high` / `medium` / `low` |
| `tags` | string[] | 是 | [] | 标签列表 |
| `summary` | string | 是 | - | 内容摘要（<=80字符，自动生成） |
| `expires` | string \| null | 是 | null | 过期日期 ISO 8601，null=永不过期 |
| `related_files` | string[] | 是 | [] | 关联文件路径列表 |
| `last_modified` | string (ISO 8601) | 是 | - | 最后修改时间，含时区 |
| `emphasis` | boolean | 是 | false | 用户主动强调/标记重点 |
| `mention_count` | integer | 否 | 0 | 提及次数（skill 类别，>=3视为反复提及） |

### project 类别额外字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `project_name` | string | 是 | 项目名称 |
| `status` | string | 是 | `active` / `paused` / `completed` / `archived` |
| `decision_log` | DecisionEntry[] | 否 | 决策日志 |

### DecisionEntry 结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | string (ISO 8601) | 决策时间 |
| `decision` | string | 决策内容简述 |
| `entry_id` | string | 关联的条目ID |

---

## 二、habit / skill 文件示例

```yaml
---
entry_id: "2026-07-19-12-00-001"
date: "2026-07-19T12:00:00+08:00"
category: habit
priority: high
tags: [交互风格, emoji]
summary: "用户明确要求永远不要使用emoji"
expires: null
related_files: []
last_modified: "2026-07-19T12:00:00+08:00"
emphasis: true
mention_count: 0
---

正文内容（Markdown格式）...
```

---

## 三、project 文件示例

```yaml
---
entry_id: "2026-07-19-12-00-001"
date: "2026-07-19T12:00:00+08:00"
category: project
project_name: "data_platform"
status: active
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
mention_count: 0
---

项目正文（Markdown格式）...
```

---

## 四、总目录文件 memory_index.md

### 顶层结构

```yaml
---
last_modified: "2026-07-19T12:00:00+08:00"
entries:
  - <Entry 对象>
  - ...
---
```

### Entry 对象字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 相对于 memory 目录的文件路径 |
| `category` | string | 是 | habit / skill / project |
| `summary` | string | 是 | 内容摘要 |
| `priority` | string | 是 | high / medium / low |
| `tags` | string[] | 是 | 标签列表 |
| `entry_id` | string | 是 | 唯一ID |
| `last_modified` | string (ISO 8601) | 是 | 最后修改时间 |
| `emphasis` | boolean | 是 | 是否用户强调 |
| `mention_count` | integer | 否 | 提及次数（skill 类别） |
| `title` | string | 否 | 项目标题（project 类别） |

### 完整示例

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

---

## 五、归档文件

归档文件与原文件格式完全相同，只是存放在 `archive/` 子目录下。归档后 `memory_index.md` 中对应条目的 `path` 更新为归档路径。

---

## 六、字段类型速查

| 类型 | YAML 表示 | 示例 | 说明 |
|------|----------|------|------|
| ISO 8601 时间 | string | `"2026-07-19T12:00:00+08:00"` | 必须含时区 |
| ISO 8601 日期 | string | `"2027-12-31"` | 仅日期，用于 expires |
| 枚举字符串 | string | `"high"` / `"medium"` / `"low"` | 仅限预定义值 |
| 字符串数组 | sequence | `[tag1, tag2]` | 方括号表示 |
| 布尔值 | boolean | `true` / `false` | 全小写 |
| 空值 | null | `null` | 表示无/未设置 |

---

## 七、常见错误

### 错误1：缺少时区

```yaml
# 错误
last_modified: "2026-07-19T12:00:00"
# 正确
last_modified: "2026-07-19T12:00:00+08:00"
```

### 错误2：entry_id 格式不规范

```yaml
# 错误
entry_id: "entry_001"
entry_id: "1687610000"
# 正确
entry_id: "2026-07-19-12-00-001"
```

### 错误3：手动编辑 front matter 后索引不同步

手动编辑记忆文件后必须执行 `python cli.py rebuild --json` 重建索引。
