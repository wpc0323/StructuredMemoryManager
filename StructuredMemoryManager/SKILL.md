---
name: StructuredMemoryManager
version: 3.0.0
description: "【每次新对话开始时必须首先调用】预加载用户偏好、习惯、历史决策等高优记忆，确保回复符合用户要求。也用于记录新偏好/习惯、保存任务总结、存储项目决策。"
license: MIT
category: memory-management
tags:
  - memory
  - structured-storage
  - yaml-index
  - retrieval
  - agent-memory
  - vector-search

entry_point: scripts/cli.py
system_prompt: prompts/system.md

dependencies:
  python: ">=3.8"
  libraries:
    - name: PyYAML
      version: ">=5.0"
      fallback: "内置YAML解析器（功能受限）"
    - name: chromadb
      version: ">=0.5.0"
      optional: true
      fallback: "降级为关键字匹配检索"
      note: "首次使用时自动下载嵌入模型 all-MiniLM-L6-v2（约86MB）到 .cache/ 目录；可通过 scripts/download_model.py 从 hf-mirror.com 加速下载"

permissions:
  - read_write_workspace
  - directory_access:
      path: StructuredMemoryManager/
      operations: [read, write, create, delete]
  - shell_execute:
      description: "当 Agent 遇到需要记忆的事件时（如用户表达偏好、完成任务、做出重要决策等）。当 Agent 需要检索旧记忆时（如新对话、执行任务前）"
      commands:
        - "python {{SKILL_DIR}}/scripts/cli.py *"
---

# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。
> v3.0 加入向量数据库（ChromaDB）语义检索能力。
## 描述

- 当 Agent 遇到需要记忆的事件时（如用户表达偏好、完成任务、做出重要决策等）。
- 当 Agent 需要检索旧记忆时（如新对话、执行任务前）。
## 核心原则

一旦加载此 Skill，Agent 的默认记忆行为即被接管。
**绝对禁止直接使用文件写入工具创建/修改任何记忆文件**，
所有记忆操作必须且只能通过 `cli.py` 执行。

## 执行方式

所有工具方法通过 Shell 执行 `scripts/cli.py` 调用，命令格式：

```
python "{CLI_PATH}" <command> [args...] --json
```

Agent 加载时应定位 `cli.py` 的绝对路径，后续所有调用均使用该路径。

## 检索模式（v3.0 新增）

| 模式 | 触发条件 | 说明 |
|------|---------|------|
| **向量模式**（默认） | chromadb 已安装 | 用嵌入模型做语义相似度检索，再按权重综合排序 |
| **关键字模式**（降级） | chromadb 未安装，或显式 `--no-vector` | 现有逻辑：总目录关键字匹配 → 独立文件精读 |

向量模式的优势：
- 支持**自然语言查询**（"我之前说过的关于 UI 偏好的事"）
- **语义相似**而非字面匹配（"不使用表情符号"能匹配到"emoji"）
- 仍然遵循原有的**加权检索规范**（分类权重、emphasis、priority 等全部保留）

## 使用场景

| 触发信号 | 命令 |
|---------|------|
| 用户表达偏好/习惯 | `python "{CLI}" add -c habit --content "..." -p high --emphasis --json` |
| 完成任务后总结方法 | `python "{CLI}" add -c skill --content "..." -p medium -t "标签" --json` |
| 项目中做出重要决策 | `python "{CLI}" add -c project --content "..." -p high --project-name "xxx" --json` |
| 新对话/执行任务前检索 | `python "{CLI}" search "关键词" --high-priority --json` |
| 自然语言语义检索 | `python "{CLI}" search "我之前说过的关于..." --json` |
| 强制使用关键字检索 | `python "{CLI}" search "..." --no-vector --json` |
| 查看某条记忆完整内容 | `python "{CLI}" read "habits/xxx.md" --json` |
| 确认/更新记忆状态 | `python "{CLI}" confirm "<path>" "<id>" <action> --json` |
| 索引不一致时修复 | `python "{CLI}" rebuild --json` |

## 加载指令

1. 读取 `prompts/system.md` 作为持久化系统指令并严格遵守
2. 定位 `scripts/cli.py` 的绝对路径（记为 `{CLI}`）
3. 执行 `python "{CLI}" search "" --high-priority --json` 预加载全部高优记忆
4. 若初始化失败，执行 `python "{CLI}" rebuild --json` 重建索引（会同步重建向量库）

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # 本文件（Skill 入口定义）
├── prompts/
│   └── system.md              # Agent 持久化系统指令（含完整命令模板和规则）
├── scripts/
│   ├── cli.py                 # ★ 统一调度入口
│   ├── _base.py               # 共享基础模块
│   ├── vector_store.py        # ★ 向量数据库封装（ChromaDB）
│   ├── add_memory.py          # 添加记忆（含向量库同步）
│   ├── search_memory.py       # 检索记忆（向量/关键字双模式）
│   ├── confirm_memory.py      # 确认/更新记忆（含向量库同步）
│   ├── rebuild_index.py       # 重建索引（含向量库重建）
│   └── download_model.py      # ★ 嵌入模型下载工具（HF 镜像加速）
├── .cache/                    # ★ 本地缓存（嵌入模型+chroma，自动下载）
├── templates/                 # 初始化模板
└── references/                # 参考资料
```

