# Integrations：用 Hooks 让记忆"确定发生"

StructuredMemoryManager 默认依赖 Agent 自觉触发（读 SKILL.md 后遵守）。
对支持 hooks 的 Agent（ZCode、Claude Code 等），可以把"新对话预加载高优记忆"
变成**确定执行的钩子**，不再依赖模型是否想起来调用 Skill。

## 工作原理

`scripts/session_start_hook.py` 在会话启动时：

1. 以**关键字模式**检索全部高优先级记忆（不触碰 chromadb / 嵌入模型，
   零网络、零下载，保证启动速度）；
2. 把记忆格式化为约束清单，以 hook 兼容的 JSON
   `{"additionalContext": "..."}` 输出，由客户端注入会话上下文；
3. 任何异常都静默吞掉并 exit 0 —— hook 失败绝不阻塞会话。

## ZCode 配置

hooks 配置在配置文件的 `hooks` 键下（**必须设置 `hooks.enabled: true`**，
否则配置文件 hooks 默认不运行）：

- 个人全局：`~/.zcode/cli/config.json`
- 团队共享（随仓库走）：`<repo>/.zcode/config.json`

### 示例一：Skill 安装在当前工作区 `.zcode/skills/` 下（团队共享）

```json
{
  "hooks": {
    "enabled": true,
    "events": {
      "SessionStart": [
        {
          "matcher": "startup|resume",
          "hooks": [
            {
              "type": "process",
              "command": "python",
              "args": [
                "${ZCODE_PROJECT_DIR}/.zcode/skills/StructuredMemoryManager/scripts/session_start_hook.py"
              ],
              "timeoutMs": 10000,
              "statusMessage": "加载 StructuredMemoryManager 高优先级记忆"
            }
          ]
        }
      ]
    }
  }
}
```

### 示例二：Skill 安装在自定义位置（个人全局）

把 `args` 中的路径替换为你机器上 `session_start_hook.py` 的绝对路径即可。

### 说明

- `type: "process"` 以参数向量方式运行、不经过 shell，是跨平台（Windows/macOS/Linux）
  最稳的选择；`timeoutMs` 单位为毫秒。
- `matcher: "startup|resume"` 表示新开会话和恢复会话时预加载；省略 matcher
  则 clear/compact 时也会触发。
- matcher 是大小写敏感的正则；事件名固定为 `SessionStart`。
- 修改后如未生效，检查 `hooks.enabled` 是否为 true、Python 是否在 PATH 中。

## Claude Code 配置（参考）

Claude Code 的 hooks 配置在 `~/.claude/settings.json`（或项目
`.claude/settings.json`），结构类似，用 command 类型：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "python \"/绝对路径/StructuredMemoryManager/scripts/session_start_hook.py\""
          }
        ]
      }
    ]
  }
}
```

## 其他 Agent（Trae / Cursor 等）

不支持 hooks 的环境维持原有方式即可：Skill 加载后 Agent 会按
`prompts/system.md` 的初始化清单执行
`python "{CLI}" search "" --high-priority --json` 完成预加载。
也可以把这一行加进 Agent 的全局规则文件（如 `.cursorrules`），
让每次会话开始时必然执行。

## 可选：会话结束自动写记忆（不建议默认开启）

`Stop` 事件同样可以接 hook，但"自动总结并写入记忆"涉及内容判断，
容易产生低质量记忆（本项目的自动去重可以兜底一部分）。
建议保持由 Agent 在对话中按 `add` 场景主动记录，`Stop` hook 仅用于提示
而非自动写入。如确有需要，可自行参考上方格式接入。
