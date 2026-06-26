# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。

## 简介

StructuredMemoryManager 是一个全面接管 Agent 记忆生成、存储、索引和检索行为的 Skill 包。它替代默认的按时间分文件记忆方式，提供：

- **三分类存储**：习惯偏好、技能方法、项目详情分而治之
- **YAML 结构化索引**：每个文件都有完整的元数据和内部索引
- **三级检索机制**：总目录 → 内部索引 → 正文，高效精准
- **优先级与保鲜期**：高优记忆永不丢失，临时信息自动过期
- **自动归档**：超阈值时自动归档低优先级旧条目
- **跨文件关联**：记忆之间建立显式引用关系

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # Skill 主定义（入口）
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
- 创建 `memory/` 目录
- 从模板初始化 `memory_index.md`
- 扫描高优先级标签并预加载

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
         content="用户明确要求不要使用emoji符号，在所有输出中避免使用表情符号",
         priority="high",
         tags=["交互风格", "格式限制"]
       )

用户: 帮我把这个React组件优化一下
Agent: [优化完成后调用] add_memory(
         category="skill",
         content="React Hooks性能优化：useMemo缓存计算、useCallback稳定引用...",
         priority="medium",
         tags=["React", "性能优化"],
         expires="2027-06-24"
       )
```

#### 检索记忆 — 调用 `search_memory()`

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

#### 维护记忆 — 调用 `confirm_memory()` / `rebuild_index()`

| 操作 | 触发时机 | 说明 |
|------|---------|------|
| `confirm` | 定期检查时确认某条记忆仍有效 | 设为永不过期 |
| `extend` | 快过期但仍有用的记忆 | 延长有效期（如再延1年） |
| `upgrade` | 用户再次强调某偏好 / 发现比预期更重要 | 升为 high，永不归档 |
| `downgrade` | 已不再重要的旧信息 | 降为 low，纳入归档候选 |
| `rebuild_index` | 索引与正文不一致 / 手动编辑后修复 | 全量重建内部索引 |

### 对于开发者（手动测试）

可通过命令行直接测试工具：

```bash
# 添加一条记忆
python scripts/add_memory.py \
  --category habit \
  --content "用户偏好深色主题" \
  --priority high \
  --tags "UI风格"

# 搜索记忆
python scripts/search_memory.py "UI风格" --category habit

# 确认记忆
python scripts/confirm_memory.py habits_preferences.md 2026-06-24-15-30-001 confirm

# 重建索引
python scripts/rebuild_index.py habits_preferences.md

# 批量重建所有索引
python scripts/rebuild_index.py --all
```

## 核心工具方法

| 方法 | 功能 | 触发时机 |
|------|------|---------|
| `add_memory()` | 添加记忆并维护索引 | Agent 需要持久化信息时 |
| `search_memory()` | 三级检索记忆 | Agent 需要回忆信息时 |
| `confirm_memory()` | 确认/更新记忆状态 | 维护、到期确认、优先级调整 |
| `rebuild_index()` | 重建文件索引 | 索引与正文不一致时修复 |

## 记忆分类

| 分类 | 存储文件 | 适用内容 |
|------|---------|---------|
| `habit` | `habits_preferences.md` | 交互风格、审美倾向、语言习惯 |
| `skill` | `skills_methods.md` | 工具用法、工作流、代码模式 |
| `project` | `projects/<名称>.md` | 项目目标、状态、决策日志 |

## 优先级体系

| 级别 | 行为 | 典型场景 |
|------|------|---------|
| `high` | 永不归档，启动时预加载 | 硬性约束（如"不要生成图片"） |
| `medium` | 正常保留，到期提示确认 | 稳定偏好（如"用暗色主题"） |
| `low` | 90天后纳入归档候选 | 临时信息（如"本次用Tab"） |

## 归档机制

- **触发条件**：`internal_index` 条目数 > 50
- **筛选条件**：`priority == low` 且距今 > 90 天
- **归档动作**：移至 `*_archive.md`，原文件标记归档状态
- **可恢复性**：归档不删除，检索时可查到

## 依赖

| 依赖 | 版本要求 | 必需 | 说明 |
|------|---------|------|------|
| Python | >=3.8 | 是 | 运行环境 |
| PyYAML | >=5.0 | 推荐 | YAML解析，无则启用内置简易解析器 |

## 许可证

MIT License

## 设计文档

- [使用案例](references/usage_examples.md) - 7个典型场景的完整操作演示
- [Schema 参考](references/schema_guide.md) - 所有 YAML 字段的类型定义与规范
- [最佳实践](references/best_practices.md) - 设计思路、优先级策略、归档原理
