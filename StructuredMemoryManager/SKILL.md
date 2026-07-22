---
name: StructuredMemoryManager
version: 2.0.0
description: "基于独立文件存储、YAML索引和加权二级检索机制的长期记忆管理skill。通过 Shell 执行 cli.py 进行记忆操作。"
license: MIT
category: memory-management
tags:
  - memory
  - structured-storage
  - yaml-index
  - retrieval
  - agent-memory

entry_point: scripts/cli.py
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
  - shell_execute:
      description: "通过 Shell 执行 cli.py 进行记忆操作"
      commands:
        - "python {{SKILL_DIR}}/scripts/cli.py *"
---

# StructuredMemoryManager

> 让 Agent 告别"失忆"和"模糊记忆"的结构化长期记忆管理 Skill。

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

## 使用场景

| 触发信号 | 命令 |
|---------|------|
| 用户表达偏好/习惯 | `python "{CLI}" add -c habit --content "..." -p high --emphasis --json` |
| 完成任务后总结方法 | `python "{CLI}" add -c skill --content "..." -p medium -t "标签" --json` |
| 项目中做出重要决策 | `python "{CLI}" add -c project --content "..." -p high --project-name "xxx" --json` |
| 新对话/执行任务前检索 | `python "{CLI}" search "关键词" --high-priority --json` |
| 查看某条记忆完整内容 | `python "{CLI}" read "habits/xxx.md" --json` |
| 确认/更新记忆状态 | `python "{CLI}" confirm "<path>" "<id>" <action> --json` |
| 索引不一致时修复 | `python "{CLI}" rebuild --json` |

## 加载指令

1. 读取 `prompts/system.md` 作为持久化系统指令并严格遵守
2. 定位 `scripts/cli.py` 的绝对路径（记为 `{CLI}`）
3. 执行 `python "{CLI}" search "偏好 习惯 规范" --high-priority --json` 预加载高优记忆
4. 若初始化失败，执行 `python "{CLI}" rebuild --json` 重建索引

## 文件结构

```
StructuredMemoryManager/
├── SKILL.md                   # 本文件（Skill 入口定义）
├── prompts/
│   └── system.md              # Agent 持久化系统指令（含完整命令模板和规则）
├── scripts/
│   ├── cli.py                 # ★ 统一调度入口
│   ├── _base.py               # 共享基础模块
│   ├── add_memory.py          # 添加记忆（cli.py 内部调用）
│   ├── search_memory.py       # 检索记忆（cli.py 内部调用）
│   ├── confirm_memory.py      # 确认/更新记忆（cli.py 内部调用）
│   └── rebuild_index.py       # 重建索引（cli.py 内部调用）
├── templates/                 # 初始化模板
└── references/                # 参考资料
```
