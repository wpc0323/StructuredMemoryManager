# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。
> v3.0 加入向量数据库（ChromaDB）语义检索能力；v3.1 修复降级检索与 YAML 回退解析缺陷，新增 `stats` 健康检查、pytest 测试套件与 CI；v3.2 新增自动去重、删除/维护命令、Hooks 自动预加载与原子写入保护。

## 简介

StructuredMemoryManager 是一个全面接管 Agent 记忆生成、存储、索引和检索行为的 Skill 包。它替代默认的按时间分文件记忆方式，提供：

- **三分类存储**：习惯偏好、技能方法、项目详情分而治之
- **独立文件**：每条记忆一个 `.md` 文件，按类别存入子目录
- **YAML 结构化索引**：全局 `memory_index.md` 维护所有条目的元数据
- **★ 向量语义检索**（v3.0）：基于 ChromaDB + all-MiniLM-L6-v2 嵌入模型，支持自然语言查询和语义相似匹配
- **加权检索**：向量相似度 × 分类权重 × emphasis × priority × recency 综合排序
- **双模式自动降级**：chromadb 不可用时自动回退到关键字匹配检索
- **★ 检索空结果自动回退**（v3.1）：向量库为空或查询失败时自动改用关键字检索，不再返回空结果
- **强调与提及追踪**：用户主动强调的内容和反复提及的技能获得最高权重
- **优先级与保鲜期**：高优记忆永不丢失，临时信息自动过期
- **自动归档**：超阈值时自动归档低优先级旧条目
- **统一 CLI 入口**：所有操作通过 `cli.py` 执行，Agent 无需直接调用 Python 函数
- **stats 健康检查**（v3.1）：一条命令查看记忆库文件数、索引条数与向量库状态
- **pytest 测试套件 + CI**（v3.1）：覆盖回退解析、加权检索、归档与 CLI 端到端
- **自动去重合并**（v3.2）：重复记录不再产生新文件，合并进原记忆并自动升级提及计数/强调/优先级
- **删除与维护**（v3.2）：`delete` 软删除可恢复（同步向量库），`maintenance` 列出过期/归档候选/长期未更新条目
- **Hooks 自动预加载**（v3.2）：SessionStart 钩子自动注入高优记忆，不再依赖 Agent 自觉触发
- **原子写入 + 进程锁**（v3.2）：临时文件 + `os.replace` 原子替换，锁保护索引读改写，多会话并发不再写坏索引

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # Skill 主定义（入口）
├── prompts/
│   └── system.md              # Agent 持久化系统指令
├── scripts/
│   ├── cli.py                 # ★ 统一调度入口（Agent 唯一调用入口）
│   ├── _base.py               # 共享基础模块（YAML解析、加权算法、原子写入、进程锁）
│   ├── vector_store.py        # ★ 向量数据库封装（ChromaDB）
│   ├── add_memory.py          # 添加记忆（自动去重合并 + 向量库同步）
│   ├── search_memory.py       # 检索记忆（向量/关键字双模式）
│   ├── confirm_memory.py      # 确认/更新记忆（含向量库同步）
│   ├── delete_memory.py       # 删除记忆（默认软删除到 deleted/）
│   ├── maintenance.py         # 记忆维护检查（过期/归档候选/长期未更新）
│   ├── session_start_hook.py  # ★ SessionStart hook 预加载脚本
│   ├── rebuild_index.py       # 重建索引（含向量库重建）
│   └── download_model.py      # ★ 嵌入模型下载工具（HF 镜像加速）
├── .cache/                    # ★ 本地缓存（嵌入模型+chroma，自动下载，~86MB）
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
├── .gitignore                 # Git 忽略规则（含 .cache/、__pycache__/ 排除）
├── integrations/              # Hooks 接入指南（ZCode / Claude Code）
├── tests/                     # pytest 测试套件
└── .github/
    └── workflows/ci.yml       # CI（Python 3.9~3.12 + 无PyYAML回退模式）
```

## 安装

### 前置要求

- Python 3.8+
- PyYAML >= 5.0（可选，有内置回退方案）
- chromadb >= 0.5.0（可选，启用向量语义检索；未安装时自动降级为关键字匹配）
- onnxruntime + tokenizers + tqdm（chromadb 的嵌入模型依赖，随 chromadb 安装）

### 安装步骤

1. 将整个 `StructuredMemoryManager/` 目录复制到 Agent 的 Skills 目录下
2. 确保 `SKILL.md` 可被 Agent 的 skill 加载器正确识别
3. （可选）安装 PyYAML 以获得更好的 YAML 解析能力：
   ```bash
   pip install pyyaml
   ```
4. （推荐）安装 chromadb 启用向量语义检索：
   ```bash
   pip install chromadb
   ```
   首次使用向量检索时，ChromaDB 会自动下载 all-MiniLM-L6-v2 ONNX 嵌入模型（约 86MB）到 `.cache/` 目录。
   如自动下载缓慢，可手动执行加速下载：
   ```bash
   python scripts/download_model.py
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

### 环境变量

| 变量 | 说明 |
|------|------|
| `SMM_MEMORY_DIR` | 显式指定记忆目录，覆盖自动检测（便于多套记忆隔离与测试） |
| `SMM_NO_VECTOR` | 设为 `1` 时全局禁用向量检索，强制关键字模式（离线环境/排障用） |
| `HF_ENDPOINT` | HuggingFace 镜像地址，默认 `https://hf-mirror.com`（download_model.py 使用） |

### 验证安装

```bash
python scripts/cli.py add -c habit --content "测试记忆" -p high -t "测试" --emphasis --json
python scripts/cli.py search "测试" --json
```

## 使用方式

### 检索模式（v3.0 新增）

| 模式 | 触发条件 | 说明 |
|------|---------|------|
| **向量模式**（默认） | chromadb 已安装 | 用嵌入模型做语义相似度检索，再按权重综合排序 |
| **关键字模式**（降级） | chromadb 未安装，或显式 `--no-vector` | 总目录关键字匹配 → 独立文件精读 |

向量模式的优势：
- 支持**自然语言查询**（如 "我之前说过的关于 UI 偏好的事"）
- **语义相似**而非字面匹配（"不使用表情符号"能匹配到"emoji"）
- 仍然遵循原有的**加权检索规范**（分类权重、emphasis、priority 等全部保留）

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
| 自然语言语义检索 | "我之前说过的关于 UI 偏好的事" | `python "{CLI}" search "我之前说过的关于 UI 偏好的事" --json` |
| 用户问过往信息 | "我之前说过什么？" | `python "{CLI}" search "..." --json` |
| 执行任务前检查约束 | 要生成图片前检查是否允许 | `python "{CLI}" search "图片" --high-priority --json` |
| 查找历史经验 | 类似任务需要参考之前的做法 | `python "{CLI}" search "关键词" -t "标签" --json` |
| 项目进展查询 | "我的项目现在什么状态？" | `python "{CLI}" search "进展" --category project --json` |
| 强制关键字检索 | 需要精确匹配而非语义匹配 | `python "{CLI}" search "..." --no-vector --json` |

**检索结果按加权权重降序排列**，高权重记忆优先纳入上下文。
向量模式下每条结果包含 `similarity` 字段（0~1，越大越相似）。

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
| `stats` | `python "{CLI}" stats --json` | 查看记忆库健康状态（文件数、索引条数、向量库可用性） |
| `maintenance` | `python "{CLI}" maintenance --json` | 列出过期/归档候选/长期未更新/索引缺失条目 |
| `delete` | `python "{CLI}" delete "<path>" --json` | 删除记忆（默认软删除可恢复，`--hard` 永久删除） |
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
| `add_memory()` | `cli.py add` | 添加记忆并维护索引（同步写入向量库） | Agent 需要持久化信息时 |
| `search_memory()` | `cli.py search` | 向量/关键字双模式加权检索 | Agent 需要回忆信息时 |
| `read_memory()` | `cli.py read` | 读取单条记忆完整内容 | 需要查看某条记忆的详情 |
| `confirm_memory()` | `cli.py confirm` | 确认/更新记忆状态（同步更新向量库元数据） | 维护、到期确认、优先级调整、强调标记 |
| `delete_memory()` | `cli.py delete` | 删除记忆（默认软删除到 deleted/，同步向量库） | 用户否认某条记忆、记忆错误或彻底过时 |
| `maintenance()` | `cli.py maintenance` | 列出过期/归档候选/长期未更新/索引缺失条目 | 定期健康检查 |
| `rebuild_index()` | `cli.py rebuild` | 重建文件索引+向量库 | 索引与正文不一致时修复 |

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

项目自带 pytest 测试套件，覆盖：YAML 回退解析器（含跨环境读写兼容）、加权检索排序、
添加/检索/确认/重建全流程、归档机制、路径越界防护、CLI 子进程端到端。

```bash
pip install pytest
pytest tests/ -v
```

GitHub Actions CI 会在 Python 3.9 ~ 3.12 上运行测试，并额外覆盖"无 PyYAML 回退模式"。

手动端到端冒烟测试：

```bash
python scripts/cli.py add -c habit --content "测试记忆" -p high -t "测试" --emphasis --json
python scripts/cli.py search "测试" --json
python scripts/cli.py rebuild --json
python scripts/cli.py stats --json
```

## 依赖

| 依赖 | 版本要求 | 必需 | 说明 |
|------|---------|------|------|
| Python | >=3.8 | 是 | 运行环境 |
| PyYAML | >=5.0 | 推荐 | YAML解析，无则启用内置简易解析器 |
| pytest | >=7.0 | 开发 | 运行测试套件 |

## 可靠性与维护（v3.2 新增）

### 自动去重

`add` 默认开启去重，解决"同一偏好被反复记录导致文件膨胀"：

- **精确匹配**：新内容归一化后与已有摘要相同、或已包含在正文中 → 合并
- **向量匹配**（chromadb 可用时）：语义相似度 ≥ 0.95 → 合并（阈值经文本核对，
  避免误合并；旧版相似度映射会把所有结果垫高到 1/3 以上，v3.2 已校准）
- **合并是无损的**：新内容追加进原文件正文（逐字重复不重复追加），skill 的
  `mention_count` +1，`emphasis`/更高优先级会传播，索引与向量库同步更新
- 确需另存新条目时加 `--no-dedup`

### 删除记忆

记忆系统必须能"遗忘"。`delete` 默认软删除：文件移入该类别 `deleted/` 子目录
（可手动移回恢复），索引与向量库同步移除、检索不再命中，且 `rebuild`
不会让已删除记忆复活。`--hard` 永久删除。

### 记忆维护

`maintenance` 让保鲜期体系可执行：列出已过期（建议 confirm/extend/downgrade）、
归档候选、medium 超 180 天未更新（建议向用户确认）、索引缺失文件（建议 rebuild）
的条目清单。

### 原子写入与并发保护

- 所有记忆文件和索引的写入都是"临时文件 + `os.replace`"原子替换，崩溃不会留下半截文件
- `add`/`confirm`/`delete`/`rebuild` 全程持有跨进程锁（`.index.lock`），
  多会话并发操作不会互相覆盖索引；锁超时自动降级不阻塞，残留锁自动清理
- 索引路径统一 POSIX 正斜杠，记忆目录可跨操作系统同步

### Hooks 自动预加载

在 ZCode / Claude Code 中配置 SessionStart 钩子后，每次会话开始自动注入
全部高优先级记忆（关键字模式、零网络依赖、失败静默不影响会话）。
配置示例见 [integrations/README.md](integrations/README.md)。

## 设计文档

- [使用案例](references/usage_examples.md) - 8个典型场景的完整操作演示
- [Schema 参考](references/schema_guide.md) - 所有 YAML 字段的类型定义与规范
- [最佳实践](references/best_practices.md) - 设计思路、优先级策略、归档原理

## 许可证

MIT License

---

