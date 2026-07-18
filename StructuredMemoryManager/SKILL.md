---
name: StructuredMemoryManager
version: 1.0.0
description: "基于结构化文件、YAML索引和三级检索机制的长期记忆管理skill，替代默认按时间分文件的记忆方式。当需要记录用户偏好、保存技能方法、检索历史记忆、维护记忆状态时调用此Skill。"
author: Agent Skill System
license: MIT
category: memory-management
tags:
  - memory
  - structured-storage
  - yaml-index
  - retrieval
  - agent-memory

entry_point: scripts/
system_prompt: prompts/system.md

dependencies:
  python: ">=3.8"
  libraries:
    - name: PyYAML
      version: ">=5.0"
      fallback: "内置YAML解析器（功能受限）"

permissions:
  - read_write_workspace
  - directory_access:
      path: StructuredMemoryManager/
      operations: [read, write, create, delete]
---

# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。

## 核心原则

一旦加载此 Skill，Agent 的默认记忆行为即被接管。
**绝对禁止直接使用文件写入工具创建/修改任何记忆文件**，
所有记忆操作必须且只能通过本 Skill 提供的工具方法完成。

## 使用场景（何时调用）

### 写入记忆 — 调用 `add_memory()`

| 触发信号 | 示例 | 调用方式 |
|---------|------|---------|
| 用户表达偏好/习惯 | "我喜欢简洁的代码"、"不要用emoji"、"以后都用中文回复" | `add_memory(category="habit", priority="high")` |
| 完成任务后总结方法 | "这个React优化模式可以记下来"、"批量处理的脚本写法" | `add_memory(category="skill", priority="medium", expires="1年后")` |
| 项目中做出重要决策 | "决定用PostgreSQL"、"选择微服务架构" | `add_memory(category="project", priority="high", project_name="xxx")` |
| 出现临时约定/要求 | "本次任务用Tab缩进"、"这个项目必须用TypeScript" | `add_memory(priority="low")` |
| 需要长期记住的信息 | 用户提供了账号配置、环境要求、背景信息 | `add_memory(...)` |

**典型对话示例**：

```
用户: 我讨厌emoji，以后别用了
Agent: [立即调用] add_memory(
         category="habit",
         content="用户明确要求不要使用emoji符号",
         priority="high",
         tags=["交互风格"]
       )

用户: 帮我把这个React组件优化一下
Agent: [优化完成后] add_memory(
         category="skill",
         content="React Hooks性能优化模式...",
         priority="medium",
         tags=["React", "性能优化"]
       )
```

### 检索记忆 — 调用 `search_memory()`

| 触发信号 | 示例 | 调用方式 |
|---------|------|---------|
| 新对话开始 | 需要加载用户的历史偏好和约束 | `search_memory(query="偏好习惯", category_filter="habit", high_priority_only=True)` |
| 用户问过往信息 | "我之前说过什么？"、"上次怎么做的？" | `search_memory(query="...")` |
| 执行任务前检查约束 | 要生成图片前检查是否允许 | `search_memory(query="图片", high_priority_only=True)` |
| 查找历史经验 | 类似任务需要参考之前的做法 | `search_memory(query="关键词", tag_filter=["标签"])` |
| 项目进展查询 | "我的项目现在什么状态？" | `search_memory(query="进展", category_filter="project")` |

**检索流程示意**：

```
用户: 帮我写个API接口
Agent: [先检索] search_memory(query="API设计 项目规范", high_priority_only=True)
      → 找到: "项目要求RESTful风格，用JWT认证"
      → 根据这些约束开始编写
```

### 维护记忆 — 调用 `confirm_memory()` / `rebuild_index()`

| 操作 | 触发时机 | 说明 |
|------|---------|------|
| `confirm` | 定期检查时确认某条记忆仍有效 | 设为永不过期 |
| `extend` | 快过期但仍有用的记忆 | 延长有效期（如再延1年） |
| `upgrade` | 用户再次强调某偏好 / 发现比预期更重要 | 升为 high，永不归档 |
| `downgrade` | 已不再重要的旧信息 | 降为 low，纳入归档候选 |
| `rebuild_index` | 索引与正文不一致 / 手动编辑后修复 | 全量重建内部索引 |

---

## 工具方法详解

### 1. add_memory — 添加记忆

添加一条新记忆并自动维护所有索引。

**何时调用：**
- 用户表达了个人偏好或习惯（"我喜欢..."、"不要..."、"以后都用..."）
- 完成任务后总结出可复用的方法/模式（"这个做法可以记下来"）
- 项目中做出重要决策需要记录（技术选型、方案确定）
- 对话中出现需要长期记住的约定或信息
- 任何你判断应该被持久化的信息

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `category` | string | 是 | - | 记忆类别：`habit`(习惯偏好) / `skill`(技能方法) / `project`(项目详情) |
| `content` | string | 是 | - | 记忆正文内容，支持Markdown格式 |
| `priority` | string | 否 | medium | 优先级：`high`(核心约束/永不归档) / `medium`(常用偏好) / `low`(临时信息) |
| `tags` | array | 否 | [] | 标签列表，用于检索和分类 |
| `expires` | string | 否 | null | 过期日期(ISO 8601)，null表示永不过期 |
| `related` | array | 否 | null | 关联文件路径列表 |
| `project_name` | string | 否*(project必填)* | - | 项目名称(category=project时必填) |
| `emphasis` | boolean | 否 | false | 是否被用户主动强调/标记重点（影响加权检索权重） |
| `mention_count` | integer | 否 | 0 | 提及次数（skill类别，>=3视为反复提及） |

---

### 2. search_memory — 检索记忆

精确检索记忆，执行加权三级检索机制（总目录→内部索引→正文）。

**何时调用：**
- 新对话开始时，需要回忆用户的历史偏好和约定
- 用户提问涉及之前的信息（"我之前说过什么？"、"上次怎么做的？"）
- 执行任务前需要检查是否有相关约束或历史经验
- 用户询问项目进展、之前的决策原因
- 任何需要从过往对话中获取上下文的场景

**加权检索规范（必须严格遵守）：**

读取存储的记忆文件时，对三类记忆分别分配差异化权重，检索排序、上下文引用均按下述优先级执行：

| 分类 | 权重排序 |
|------|---------|
| project（项目任务） | 时间时效性（近期优先）> 用户主动强调/标记重点 > 常规记录 |
| habit（用户偏好） | 用户主动强调/明确要求 > 时间时效性（最新优先） > 次要偏好 |
| skill（技能方法） | 用户主动强调/反复提及（mention_count>=3）> 其余全部 |

补充约束：
- 同一分类内，高优先级记忆必须优先纳入上下文
- 低优先级记忆不可覆盖、抵消高权重记忆
- 若出现记忆冲突，直接采信层级权重更高的信息

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | 是 | - | 检索查询词或自然语言问题 |
| `category_filter` | string | 否 | null | 类别过滤：habit / skill / project，null=不过滤 |
| `tag_filter` | array | 否 | null | 标签过滤，只返回含这些标签的条目 |
| `high_priority_only` | boolean | 否 | false | 是否仅返回高优先级条目（适合启动加载） |

**返回值：** `list[dict]`，每项包含 `file_path, entry_id, anchor, content_snippet, score, weight, priority, tags, emphasis, mention_count`

---

### 3. confirm_memory — 确认/更新记忆

确认或更新记忆的有效性、保鲜期和优先级。

**何时调用：**
- 定期维护时：检查即将过期的记忆，确认是否仍有效（action="confirm"）
- 延长有效期：某条记忆快过期但仍然有用（action="extend"）
- 提升重要性：发现某条记忆比预期更重要（action="upgrade"，变为high优先级永不归档）
- 降低优先级：某条记忆已不再那么重要（action="downgrade"）
- 用户主动确认/修改之前的偏好或约定

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | - | 目标文件路径（相对于memory目录） |
| `entry_id` | string | 是 | - | 条目ID，格式"YYYY-MM-DD-HH-MM-序号" |
| `action` | string | 是 | - | 操作类型：confirm / extend / upgrade / downgrade / emphasize / de_emphasize / bump_mention |
| `new_expires` | string | 否 | null | 新过期日期（extend时必填） |
| `new_priority` | string | 否 | null | 新优先级（upgrade/downgrade时必填） |

---

### 4. rebuild_index — 重建索引

根据指定文件的正文内容全量重建其YAML内部索引。

**何时调用：**
- 检测到记忆文件的 YAML internal_index 与正文内容不一致
- 手动编辑了记忆文件后需要重新同步索引
- 索引损坏或格式错误导致检索失败
- 从外部导入记忆数据后重建索引结构
- 定期维护时验证数据完整性

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 需要重建索引的目标文件路径 |

---

## 加载指令

加载此 Skill 时，Agent 必须：

1. 读取 `prompts/system.md` 作为持久化系统指令并严格遵守
2. 将所有记忆操作路由到本 Skill 提供的工具方法
3. 禁止直接使用文件写入工具创建或修改任何记忆文件
4. 初始化时检查 memory 目录结构和 memory_index.md 是否存在

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # 本文件（Skill 入口定义）
├── prompts/
│   └── system.md              # Agent 持久化系统指令
├── scripts/
│   ├── _base.py               # 共享基础模块（YAML解析、文件管理、时间工具）
│   ├── add_memory.py          # 添加记忆（可独立调用）
│   ├── search_memory.py       # 检索记忆（可独立调用）
│   ├── confirm_memory.py      # 确认/更新记忆（可独立调用）
│   └── rebuild_index.py       # 重建索引（可独立调用）
├── templates/
│   ├── memory_index.md        # 总目录模板
│   ├── habits_template.md     # 习惯偏好模板
│   ├── skills_template.md     # 技能方法模板
│   └── project_template.md    # 项目文件模板
├── references/
│   ├── usage_examples.md      # 典型使用案例
│   ├── schema_guide.md        # YAML Schema 完全参考
│   └── best_practices.md      # 设计思路与最佳实践
├── README.md                  # 安装与使用说明
├── LICENSE                    # MIT 许可证
└── .gitignore                 # Git 忽略规则
```
