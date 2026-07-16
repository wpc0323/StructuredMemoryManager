# StructuredMemoryManager 系统指令

> 本文件是 StructuredMemoryManager Skill 的核心规则定义。一旦加载，Agent 的默认记忆行为即被完全接管。

---

## 核心原则

**禁止裸写记忆文件。** 所有记忆操作必须且只能通过 `memory_tools.py` 提供的工具方法执行。Agent 绝对禁止直接使用通用文件写入工具创建、修改或删除任何位于 `StructuredMemoryManager/` 目录下的记忆文件。

---

## 一、记忆分类与存储架构

### 1.1 三大分类

| 分类标识 | 存储文件 | 内容范围 |
|---------|---------|---------|
| `habit` | `habits_preferences.md` | 用户交互风格、审美倾向、图片/代码偏好、语言习惯等个人化特征 |
| `skill` | `skills_methods.md` | 学到的工具用法、工作流模式、代码范式、其他skill的使用技巧 |
| `project` | `projects/<项目名>.md` | 各项目的目标、状态、决策日志、待办事项、关键技术细节 |

### 1.2 文件组织规则

- **习惯与技能**采用单一聚合文件，内部通过 YAML `internal_index` 按时间倒序管理条目。
- **项目**每个项目独立一个文件，文件名使用项目名（建议英文或拼音），存储于 `projects/` 子目录。
- 可选维护 `projects/_index.md` 作为项目清单总览。
- 所有文件均位于统一的记忆根目录下（由部署时配置决定，默认为 `StructuredMemoryManager/memory/`）。

---

## 二、YAML Front Matter 强制规范

### 2.1 总目录文件 `memory_index.md`

```yaml
---
last_modified: "2026-06-24T15:30:00+08:00"
files:
  - path: habits_preferences.md
    category: habit
    tags: [图片偏好, 代码风格, 语言习惯]
    last_modified: "2026-06-24T15:20:00+08:00"
    high_priority_tags: [图片偏好]   # 需要第一时间加载的核心标签
    related: []                      # 文件级关联
    archived: false                  # 是否已触发归档
  - path: projects/my_app.md
    category: project
    title: "MyApp项目"
    tags: [数据分析, React, Python]
    last_modified: "2026-06-24T09:00:00+08:00"
    high_priority_tags: []
    related:
      - "skills_methods.md#自动化脚本"
    archived: false
---
```

### 2.2 习惯/技能文件 Front Matter

```yaml
---
last_modified: "2026-06-24T15:30:00+08:00"
category: habit                          # 或 skill
priority_tags: [图片偏好]                # 高优标签集合（从internal_index中提取）
internal_index:                           # 核心：条目级索引数组
  - date: "2026-06-23T10:00:00+08:00"
    priority: high                        # high=核心约束(永不归档) / medium=常用 / low=临时
    summary: "用户明确要求永远不要生成图片"
    tags: ["图片偏好"]
    expires: null                         # ISO日期或null
    entry_id: "2026-06-23-10-00-001"
  - date: "2026-06-20T09:00:00+08:00"
    priority: medium
    summary: "偏好简洁UI，使用暗色主题"
    tags: ["UI风格"]
    expires: "2026-12-31"
    entry_id: "2026-06-20-09-00-001"
related_files: []                         # 引用的其他文件路径
archive: null                             # 归档后指向归档文件名
---
```

### 2.3 项目文件 Front Matter

```yaml
---
last_modified: "2026-06-24T12:00:00+08:00"
category: project
project_name: "my_app"
status: active                            # active / paused / completed / archived
priority_tags: [关键决策]
tags: [数据分析, API设计]
related_files:
  - "skills_methods.md#数据处理管道"
decision_log:                             # 决策日志索引（替代internal_index）
  - {date: "2026-06-20", decision: "选择React作为前端框架", reason: "团队熟悉度高"}
---
```

---

## 三、记忆写入流程（add_memory）

当 Agent 需要持久化信息时：

1. **调用 `add_memory(category, content, priority, tags, expires, related)`**
2. 工具内部自动完成以下全部步骤：
   - 根据 `category` 确定目标文件路径
   - 若目标文件不存在 → 从 `templates/` 复制对应模板并初始化
   - 生成唯一 `entry_id`（格式：`YYYY-MM-DD-HH-MM-NNN`）
   - 在 YAML `internal_index` 数组**顶部**插入新条目（保持时间倒序）
   - 在正文区域顶部添加 `### YYYY-MM-DD HH:MM` 标题及内容块
   - 更新 `last_modified` 为当前时间
   - 合并新标签到 `priority_tags`（去重）
   - 如有 `related` 参数，更新 `related_files`
   - 同步更新 `memory_index.md` 中对应文件记录的时间戳和标签
   - **归档检查**：若 internal_index 条目数 > 50，触发归档流程（见第六节）
3. **同步保证**：写入完成后，YAML 索引与正文内容必须严格一致。若出现不一致，调用 `rebuild_index` 修复。

---

## 四、记忆检索流程（search_memory — 三级检索）

**强制要求**：Agent 回忆信息时必须调用 `search_memory`，禁止自行遍历文件。

### 第一级：总目录粗筛

```
读取 memory_index.md → 解析 YAML files 列表
→ 根据 query 关键词匹配 tags / high_priority_tags
→ 结合 category_filter 缩小范围
→ 输出候选文件列表（通常 1-3 个）
```

### 第二级：内部索引精读

```
打开候选文件 → 仅解析 YAML internal_index（不读正文！）
→ 按 query 匹配 summary 和 tags
→ 应用 tag_filter 和 high_priority_only 过滤
→ 按 priority 和 date 排序
→ 输出匹配的 entry_id 列表
```

### 第三级：正文精准提取

```
根据 entry_id 定位正文中对应的 ### 标题块
→ 精确读取该条目完整内容
→ 返回 {file_path, entry_id, anchor, content} 给 Agent
```

### 未命中处理

- 若未找到结果，检查 `archived` 标记，尝试查询归档文件
- 归档文件中仍未找到，向用户反馈并建议手动确认
- **绝对禁止**在检索过程中一次性加载习惯/技能文件的全部正文内容

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
  - Agent 应主动调用 `confirm_memory(file_path, entry_id)` 确认是否仍有效
  - 若未确认，自动将 priority 降为 `low`
- `null` 或省略表示永不过期

### 5.3 高优标签（high_priority_tags）

- 在 `memory_index.md` 和各文件 front matter 中标注
- Agent 启动或对话初始化时应**首先扫描**这些标签对应的内容
- 确保"硬性约束"类记忆被第一时间加载到上下文

---

## 六、长期维护与归档机制

### 6.1 归档触发条件

当 `habits_preferences.md` 或 `skills_methods.md` 的 `internal_index` 条目数 **超过 50** 时，自动执行归档：

### 6.2 归档筛选逻辑

```
候选集 = internal_index 中满足以下条件的条目：
  - priority == "low"
  - 且 (当前日期 - date) > 90 天
```

### 6.3 归档执行步骤

1. 创建或追加到归档文件（`habits_archive.md` 或 `skills_archive.md`）
2. 将选中条目从原文件 `internal_index` 中移除
3. 从原文件正文中删除对应的内容块
4. 在原文件 front matter 中设置 `archive: habits_archive.md`（或 skills_archive.md）
5. 更新 `memory_index.md` 中该文件的 `archived: true` 并添加归档标签
6. 归档后若条目仍超 50，降低阈值至60天或提示用户手动清理

### 6.4 归档文件格式

归档文件与原文件格式完全相同，包含独立的 YAML front matter 和 internal_index。

---

## 七、跨文件关联机制

### 7.1 related_files 字段

用于记录文件间的引用关系，格式示例：

```yaml
related_files:
  - "skills_methods.md#自动化脚本章节"
  - "projects/data_pipeline.md#决策日志"
```

### 7.2 自动建联规则

写入记忆时，如果检测到内容涉及其他类别或已存在的主题，应自动建立关联：

- 项目文件引用了某个技能方法 → 自动添加 `related_files` 条目
- 技能方法来源于某个项目的实践 → 双向关联
- `memory_index.md` 的 `related` 字段反映文件级关联网络

### 7.3 关联的作用

- 检索时提供上下文扩展（"您是否也想查看相关的XXX？"）
- 归档时保护被高优文件引用的条目
- 帮助 Agent 理解记忆之间的依赖关系

---

## 八、强制性约束汇总

| 约束 | 说明 |
|------|------|
| 工具独占 | 所有记忆读写必须通过 memory_tools.py 工具 |
| 禁止裸写 | 禁止 Agent 直接用文件工具写记忆文件 |
| 三级检索 | search_memory 必须走 总目录→内部索引→正文 三级 |
| 正文隔离 | 检索时禁止全量加载习惯/技能文件正文 |
| 索引同步 | 写入后必须保证 YAML 索引与正文严格一致 |
| 高优优先 | 启动时优先加载 high_priority_tags 对应内容 |
| 自动归档 | 条目>50时自动归档低优旧条目 |

---

## 九、初始化检查清单

Skill 加载时，Agent 应执行以下检查：

- [ ] `memory/` 目录是否存在，不存在则创建
- [ ] `memory/memory_index.md` 是否存在，不存在则从模板初始化
- [ ] `habits_preferences.md`、`skills_methods.md` 是否存在
- [ ] `projects/` 目录是否存在
- [ ] PyYAML 库是否可用（不可用时启用回退模式）
- [ ] 扫描 `high_priority_tags` 并预加载到当前会话上下文
